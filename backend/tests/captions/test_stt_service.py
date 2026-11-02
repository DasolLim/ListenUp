import asyncio
import wave
from pathlib import Path

import pytest

from services.assemblyai import AudioFormatError, TranscriptSegment
from services.assemblyai.factory import get_transcription_service
from services.assemblyai.mock import FIXTURES_DIR, MockTranscriptionService
from services.assemblyai.real import build_url

CHUNK_MS = 200
CHUNK_BYTES = 16000 * 2 * CHUNK_MS // 1000


def wav_chunks() -> list[bytes]:
    with wave.open(str(FIXTURES_DIR / "sample_16k.wav"), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1 and w.getsampwidth() == 2
        pcm = w.readframes(w.getnframes())
    return [pcm[i : i + CHUNK_BYTES] for i in range(0, len(pcm), CHUNK_BYTES)]


async def run_pipeline(service: MockTranscriptionService) -> list[TranscriptSegment]:
    await service.start(sample_rate=16000)
    collected: list[TranscriptSegment] = []

    async def consume() -> None:
        async for segment in service.segments():
            collected.append(segment)

    consumer = asyncio.create_task(consume())
    for chunk in wav_chunks():
        await service.send_audio(chunk)
    await service.stop()
    await asyncio.wait_for(consumer, timeout=5)
    return collected


def test_wrong_sample_rate_raises_clear_error() -> None:
    service = MockTranscriptionService("family")
    with pytest.raises(AudioFormatError, match="16000 Hz mono pcm_s16le"):
        asyncio.run(service.start(sample_rate=44100))


def test_mock_yields_expected_diarized_segments() -> None:
    collected = asyncio.run(run_pipeline(MockTranscriptionService("family")))
    finals = [s for s in collected if s.is_final]
    interims = [s for s in collected if not s.is_final]

    assert [s.text for s in finals] == [
        "Are you coming over for dinner on Sunday?",
        "Yes, I'll bring dessert. What time works for everyone?",
        "Six-ish. Your grandmother is joining us too.",
        "Come earlier if you want to help cook.",
        "Deal. I'll be there by five.",
    ]
    assert [s.speaker for s in finals] == ["A", "B", "C", "A", "B"]
    assert interims, "mock must emit interim (non-final) drafts"
    # ordered by time
    ends = [s.end for s in collected]
    assert ends == sorted(ends)
    # timestamps sane
    assert all(0 <= s.start < s.end for s in collected)


def test_mock_paces_by_streamed_audio() -> None:
    async def scenario() -> tuple[int, int]:
        service = MockTranscriptionService("family")
        await service.start(sample_rate=16000)
        # stream only ~2.4s of audio: just the first fixture line should be released
        for chunk in wav_chunks()[:12]:
            await service.send_audio(chunk)
        early = service._queue.qsize()
        for chunk in wav_chunks()[12:]:
            await service.send_audio(chunk)
        late = service._queue.qsize()
        await service.stop()
        return early, late

    early, late = asyncio.run(scenario())
    assert early < late, "segments must be paced by audio, not dumped at once"
    assert early >= 1


def test_crowd_fixture_has_seven_speakers() -> None:
    collected = asyncio.run(run_pipeline(MockTranscriptionService("crowd")))
    speakers = {s.speaker for s in collected if s.is_final}
    assert speakers == {"A", "B", "C", "D", "E", "F", "G"}


def test_factory_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRANSCRIPTION_SERVICE", raising=False)
    assert isinstance(get_transcription_service(), MockTranscriptionService)


def test_real_url_requests_diarization_and_format() -> None:
    url = build_url(16000)
    assert url.startswith("wss://streaming.assemblyai.com/v3/ws?")
    assert "sample_rate=16000" in url
    assert "speaker_labels=true" in url
    assert "max_speakers=5" in url
    assert "encoding=pcm_s16le" in url
    # English-only model pinned — the multilingual default can drift languages
    assert "speech_model=universal-streaming-english" in url


def test_wav_fixture_is_16k_mono_s16le() -> None:
    path = Path(FIXTURES_DIR / "sample_16k.wav")
    with wave.open(str(path), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
