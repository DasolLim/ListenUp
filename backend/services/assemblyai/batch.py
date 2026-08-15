"""Near-real-time captions for languages AssemblyAI can't *stream* (e.g. Korean).

AssemblyAI's streaming models cover English (and 18 languages on universal-3-5-pro),
but none of them do Korean. Its async Universal-2 model does — so Korean captions
run through the same provider's batch endpoint behind the same TranscriptionService
interface (INTRODUCTION §5: one STT provider, one module).

Trade-off, stated plainly: this buffers speech into utterance-sized windows and
transcribes each one, so captions land a few seconds behind the speaker instead of
under 1 s. Windows are cut on natural pauses (RMS silence) so words aren't split.
"""

import asyncio
import io
import logging
import os
import wave
from collections.abc import AsyncIterator

import httpx
import numpy as np

from app.timing import span
from services.assemblyai.base import (
    BYTES_PER_SECOND,
    TranscriptionService,
    TranscriptSegment,
    assert_audio_format,
    assert_spoken_language,
)

logger = logging.getLogger("listenup.stt.batch")

API_BASE = "https://api.assemblyai.com/v2"
# NOTE: the singular `speech_model` field is deprecated and now 400s — the async
# API requires `speech_models` as a LIST. universal-2 is the 99-language model
# that covers Korean.
SPEECH_MODELS = [os.environ.get("ASSEMBLYAI_BATCH_MODEL", "universal-2")]
MAX_SPEAKERS = 5

# Window cutting: prefer a natural pause, but never lag more than MAX_WINDOW_S.
#
# MIN_WINDOW_S is the floor on Korean caption latency (no streaming model exists
# for Korean), so it looks like the obvious latency dial. Measured, it isn't.
# Swept 1.2 / 1.6 / 2.0 / 2.5 / 3.0 against a fixed Korean set, 3 runs each,
# with the `stt_window` spans splitting the wait into buffering and API time:
#
#   MIN_WINDOW_S   char accuracy   p50 lag   api p50
#            1.2           57.5%     1.90s     1.83s
#            1.6           85.8%     2.07s     1.95s
#            2.0           97.2%     2.42s     2.00s
#            2.5           76.4%     2.33s     1.99s
#            3.0           91.5%     2.55s     2.10s
#
# The API round-trip is ~1.9-2.0s at every window size, so it — not buffering —
# is what a Korean caption is mostly waiting on. Dropping 2.0 -> 1.2 buys 0.52s
# of a 2.42s wait and costs 39.7 points of accuracy; at 1.2 the recogniser also
# began hallucinating whole sentences ("문재인 대통령은 정의당 대선 경선을...") from
# windows too short to constrain it, which in a captioning product means putting
# words in someone's mouth. 2.0 stays.
#
# The non-monotonic dip at 2.5 is a caution, not a result: where a cut lands
# relative to an utterance matters, and a single fixed audio set cannot separate
# that from a real context effect. So 2.0 is the best value measured here, not a
# proven global optimum — and the latency work that would actually pay is on the
# API round-trip, not this constant.
MIN_WINDOW_S = 2.0
MAX_WINDOW_S = 8.0
SILENCE_HOLD_S = 0.45  # trailing quiet needed to cut on a pause

# Silence detection is RELATIVE to the session's own noise floor, not a fixed
# int16 RMS. A fixed threshold (previously 320.0) is gain-dependent: measured
# against synthetic tones, quiet-but-real speech at RMS ~282 was classed as
# silence (cutting windows mid-sentence) and a low-gain mic at RMS ~106 had its
# window discarded entirely and never transcribed. That is the main cause of
# Korean captions being inconsistent, since Korean is the only language on this
# batch transport — the streaming path does its own VAD.
#
# The floor tracks the quietest audio seen this session and speech must exceed
# it by SPEECH_FACTOR, so the same code works for a whisper and a shout.
NOISE_FLOOR_START = 120.0  # assumed floor before we have measured anything
NOISE_FLOOR_MIN = 15.0     # never adapt below this (digital near-silence)
NOISE_FLOOR_DECAY = 0.92   # how fast the floor follows a quieter room
SPEECH_FACTOR = 2.2        # RMS above floor*this counts as speech
DROP_FACTOR = 1.3          # below floor*this the window is pure silence

# Bias recognition toward Korean net-slang the general model tends to mangle
# (mirrors the English keyterms on the streaming path).
KOREAN_KEYTERMS = [
    "갓생", "인싸", "아싸", "썸", "꿀잼", "노잼", "핵인싸", "존맛", "존맛탱", "맛집",
    "낄끼빠빠", "별다줄", "손절", "칼퇴", "혼밥", "혼술", "먹방", "치맥", "불금",
    "심쿵", "케미", "대박", "레알", "리얼", "오지다", "쩐다", "찜", "짱",
    "갑분싸", "TMI", "안물안궁", "어그로", "빡세다", "현타", "가성비",
]


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0


class BatchAssemblyAIService(TranscriptionService):
    """Buffers audio into utterance windows and transcribes each via the async API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ASSEMBLYAI_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "ASSEMBLYAI_API_KEY is not set — set it or use TRANSCRIPTION_SERVICE=mock"
            )
        self._language = "ko"
        self._sample_rate = 16000
        self._buffer = bytearray()
        self._queue: asyncio.Queue[TranscriptSegment | None] = asyncio.Queue()
        # Windows are transcribed concurrently but emitted in submission order —
        # see `_drain`. Each task returns its segments rather than queueing them
        # itself, which is what makes ordered emission possible.
        self._jobs: list[asyncio.Task[list[TranscriptSegment]]] = []
        self._drainer: asyncio.Task[None] | None = None
        self._next_job = 0
        self._elapsed = 0.0  # seconds of audio already flushed (segment offsets)
        self._turn = 0
        self._closed = False
        self._noise_floor = NOISE_FLOOR_START

    async def start(
        self, sample_rate: int, encoding: str = "pcm_s16le", language: str = "ko"
    ) -> None:
        assert_audio_format(sample_rate, encoding)
        assert_spoken_language(language)
        self._sample_rate = sample_rate
        self._language = language
        logger.info("batch_session_begin language=%s models=%s", language, SPEECH_MODELS)

    @property
    def _buffered_seconds(self) -> float:
        return len(self._buffer) / BYTES_PER_SECOND

    def _track_noise_floor(self, rms: float) -> None:
        """Follow the quietest recent audio, so the speech threshold adapts to
        this microphone and room instead of assuming a fixed input level."""
        if rms < self._noise_floor:
            self._noise_floor = max(NOISE_FLOOR_MIN, rms)
        else:
            # Drift up slowly so one quiet moment doesn't pin the floor forever.
            drifted = self._noise_floor * NOISE_FLOOR_DECAY + rms * (1 - NOISE_FLOOR_DECAY)
            self._noise_floor = max(NOISE_FLOOR_MIN, drifted)

    def _should_flush(self) -> bool:
        seconds = self._buffered_seconds
        if seconds >= MAX_WINDOW_S:
            return True
        if seconds < MIN_WINDOW_S:
            return False
        tail = bytes(self._buffer[-int(SILENCE_HOLD_S * BYTES_PER_SECOND) :])
        tail_rms = _rms(tail)
        self._track_noise_floor(tail_rms)
        # Cut on a pause: the tail is quiet relative to this session's floor.
        return tail_rms < self._noise_floor * SPEECH_FACTOR

    async def send_audio(self, chunk: bytes) -> None:
        if self._closed:
            return
        self._buffer.extend(chunk)
        if self._should_flush():
            self._flush()

    async def flush(self) -> None:
        """Cut the window here because the audio is about to stop.

        A pause is a real boundary in the conversation, but it is invisible to
        the windower: nothing arrives, so `_should_flush` is never consulted and
        the half-filled buffer simply waits. Whatever is said after the user
        resumes would then be appended to it and transcribed as one continuous
        utterance, however long the gap was.

        Cutting here can leave a window below `MIN_WINDOW_S`, which transcribes
        less accurately than a full one — the same trade `stop()` already makes.
        That is the better error: a short window risks a word, while merging
        risks a sentence that was never spoken.
        """
        self._flush()

    def _flush(self) -> None:
        if not self._buffer:
            return
        window = bytes(self._buffer)
        self._buffer.clear()
        offset = self._elapsed
        self._elapsed += len(window) / BYTES_PER_SECOND
        # Skip windows that are pure silence — no point paying to transcribe
        # them. Relative to the measured floor, so quiet speech is still sent.
        window_rms = _rms(window)
        if window_rms < self._noise_floor * DROP_FACTOR:
            logger.debug(
                "batch_window_dropped rms=%.1f floor=%.1f", window_rms, self._noise_floor
            )
            return
        self._jobs.append(asyncio.create_task(self._transcribe(window, offset)))
        if self._drainer is None:
            self._drainer = asyncio.create_task(self._drain())

    async def _transcribe(self, pcm: bytes, offset: float) -> list[TranscriptSegment]:
        # Measured from the window closing to the segments being available —
        # the wait a Korean caption actually pays, buffering excluded (that part
        # is MIN_WINDOW_S and is a separate decision).
        async with span(
            "stt_window",
            language=self._language,
            mode="batch",
            stage="api",
            window_s=round(len(pcm) / BYTES_PER_SECOND, 2),
        ) as perf:
            try:
                segments = await self._request(pcm, offset)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.warning("batch_window_failed error=%s", exc)
                perf["segments"] = 0
                return []
            perf["segments"] = len(segments)
            return segments

    async def _drain(self) -> None:
        """Emit finished windows **in the order they were captured**.

        Windows are transcribed in parallel, and a short one finishes long
        before a long one that came before it: a 0.2 s tail fragment beat a
        2.7 s sentence and the caption log read "쪼 내일 오후 3시에…" — the end of
        the sentence printed before its beginning.

        Out-of-order captions are bad in any transcript and worse in this one:
        someone relying on captions to follow a conversation has no audio to
        correct the order against. So the API calls stay concurrent (that is the
        latency win) while emission awaits jobs strictly in submission order.
        """
        while True:
            if self._next_job >= len(self._jobs):
                if self._closed:
                    return
                # Nothing finished to emit yet. Yield rather than spin; windows
                # are seconds apart, so this costs nothing.
                await asyncio.sleep(0.05)
                continue
            job = self._jobs[self._next_job]
            self._next_job += 1
            try:
                segments = await job
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # a failed window must not stall the rest
                logger.warning("batch_window_error error=%s", exc)
                continue
            for segment in segments:
                await self._queue.put(segment)

    async def _request(self, pcm: bytes, offset: float) -> list[TranscriptSegment]:
        headers = {"authorization": self._api_key}
        duration = len(pcm) / BYTES_PER_SECOND
        wav = _pcm_to_wav(pcm, self._sample_rate)
        async with httpx.AsyncClient(timeout=60) as client:
            upload = await client.post(f"{API_BASE}/upload", headers=headers, content=wav)
            upload.raise_for_status()
            audio_url = upload.json()["upload_url"]

            payload: dict = {
                "audio_url": audio_url,
                "language_code": self._language,
                "speech_models": SPEECH_MODELS,
                "speaker_labels": True,
                "speakers_expected": MAX_SPEAKERS,
            }
            if self._language == "ko":
                payload["word_boost"] = KOREAN_KEYTERMS
                payload["boost_param"] = "high"
            created = await client.post(
                f"{API_BASE}/transcript", headers=headers, json=payload
            )
            created.raise_for_status()
            transcript_id = created.json()["id"]

            # Poll fast at first, then back off. The old loop slept 0.5 s before
            # its *first* check, so every Korean caption paid half a second even
            # when the transcript was already finished — pure added latency on a
            # transport that is already the slow one. Short windows typically
            # complete in a few hundred milliseconds, so the early checks are
            # where the wins are; the backoff keeps a long window from making
            # hundreds of pointless requests.
            delay = 0.12
            deadline = asyncio.get_event_loop().time() + 60
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(delay)
                delay = min(delay * 1.35, 0.5)
                poll = await client.get(
                    f"{API_BASE}/transcript/{transcript_id}", headers=headers
                )
                poll.raise_for_status()
                body = poll.json()
                status = body.get("status")
                if status == "completed":
                    return self._to_segments(body, offset, duration)
                if status == "error":
                    logger.warning("batch_transcript_error %s", body.get("error"))
                    return []
        logger.warning("batch_transcript_timeout id=%s", transcript_id)
        return []

    def _to_segments(
        self, body: dict, offset: float, duration: float
    ) -> list[TranscriptSegment]:
        utterances = body.get("utterances") or []
        if not utterances:
            text = (body.get("text") or "").strip()
            if not text:
                return []
            self._turn += 1
            return [
                TranscriptSegment(
                    speaker="A",
                    text=text,
                    start=offset,
                    end=offset + duration,
                    is_final=True,
                    turn_id=self._turn,
                )
            ]
        segments = []
        for utterance in utterances:
            text = (utterance.get("text") or "").strip()
            if not text:
                continue
            self._turn += 1
            segments.append(
                TranscriptSegment(
                    speaker=str(utterance.get("speaker") or "A"),
                    text=text,
                    start=offset + (utterance.get("start") or 0) / 1000,
                    end=offset + (utterance.get("end") or 0) / 1000,
                    is_final=True,
                    turn_id=self._turn,
                )
            )
        return segments

    async def segments(self) -> AsyncIterator[TranscriptSegment]:
        while True:
            segment = await self._queue.get()
            if segment is None:
                return
            yield segment

    async def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._flush()  # transcribe whatever is left
        # Wait for the drainer, not the jobs: it is what puts segments on the
        # queue, so gathering the jobs directly would let `stop` finish — and
        # close the socket — with the last window transcribed but never sent.
        if self._drainer is not None:
            await self._drainer
        elif self._jobs:
            await asyncio.gather(*self._jobs, return_exceptions=True)
        await self._queue.put(None)
        logger.info("batch_session_end audio_s=%.1f turns=%d", self._elapsed, self._turn)
