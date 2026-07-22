"""Real AssemblyAI Universal-Streaming (v3) client with speaker diarization.

Protocol (docs, verified 2026-07): wss://streaming.assemblyai.com/v3/ws,
Authorization header = raw API key (server-side only), binary s16le frames in,
JSON Turn messages out. `speaker_labels=true` adds `speaker_label` per turn;
`max_speakers` bounds diarization (INTRODUCTION §5 speaker cap).
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from urllib.parse import urlencode

import websockets

from services.assemblyai.base import (
    TranscriptionService,
    TranscriptSegment,
    assert_audio_format,
)

logger = logging.getLogger("listenup.stt.real")

STREAMING_URL = "wss://streaming.assemblyai.com/v3/ws"
MAX_SPEAKERS = 5
# Pin the English-only model: the default (universal-3-5-pro) code-switches
# across 18 languages and can drift mid-session on ambiguous audio.
# Multilingual captions become a deliberate, user-chosen feature in Phase 4.
SPEECH_MODEL = os.environ.get("ASSEMBLYAI_SPEECH_MODEL", "universal-streaming-english")

# Bias recognition toward slang the STT otherwise mangles (e.g. "bussin" → the
# city "Busan", "rizz" → "risk"). A wrong transcript here poisons the downstream
# cultural translation, so this directly protects voice-detection accuracy.
# AssemblyAI keyterms_prompt: max 100 terms, JSON-array query param.
SLANG_KEYTERMS = [
    "bussin", "rizz", "no cap", "cap", "capping", "slay", "slaps", "mid", "ghosted",
    "ghosting", "lowkey", "highkey", "delulu", "sus", "vibe", "vibes", "drip", "flex",
    "stan", "simp", "glow up", "main character", "touch grass", "spill the tea",
    "the tea", "shook", "salty", "snatched", "periodt", "bet", "fire", "lit", "goated",
    "GOAT", "based", "cringe", "yeet", "bougie", "gyat", "aura", "mogging", "rizzler",
    "ate", "ate that up", "understood the assignment", "living rent free", "boss babe",
    "rent free", "it's giving", "npc", "ick", "gaslight", "gatekeep", "girlboss",
]


def build_url(sample_rate: int, max_speakers: int = MAX_SPEAKERS) -> str:
    params = {
        "sample_rate": sample_rate,
        "encoding": "pcm_s16le",
        "speech_model": SPEECH_MODEL,
        "speaker_labels": "true",
        "max_speakers": max_speakers,
        "format_turns": "true",
        "keyterms_prompt": json.dumps(SLANG_KEYTERMS[:100], ensure_ascii=False),
    }
    return f"{STREAMING_URL}?{urlencode(params)}"


class RealAssemblyAIService(TranscriptionService):
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ASSEMBLYAI_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "ASSEMBLYAI_API_KEY is not set — set it or use TRANSCRIPTION_SERVICE=mock"
            )
        self._ws: websockets.ClientConnection | None = None
        self._queue: asyncio.Queue[TranscriptSegment | None] = asyncio.Queue()
        self._reader: asyncio.Task[None] | None = None

    async def start(self, sample_rate: int, encoding: str = "pcm_s16le") -> None:
        assert_audio_format(sample_rate, encoding)
        self._ws = await websockets.connect(
            build_url(sample_rate),
            additional_headers={"Authorization": self._api_key},
        )
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if isinstance(raw, bytes):
                    continue
                message = json.loads(raw)
                kind = message.get("type")
                if kind == "Begin":
                    logger.info("aai_session_begin id=%s", message.get("id"))
                elif kind == "Turn":
                    segment = self._to_segment(message)
                    if segment:
                        await self._queue.put(segment)
                elif kind == "Termination":
                    logger.info(
                        "aai_session_end audio_s=%s", message.get("audio_duration_seconds")
                    )
        except websockets.ConnectionClosed as exc:
            logger.info("aai_connection_closed code=%s", exc.code)
        finally:
            await self._queue.put(None)

    @staticmethod
    def _to_segment(turn: dict) -> TranscriptSegment | None:
        text = (turn.get("transcript") or "").strip()
        if not text:
            return None
        words = turn.get("words") or []
        start_ms = words[0]["start"] if words else 0
        end_ms = words[-1]["end"] if words else 0
        return TranscriptSegment(
            speaker=turn.get("speaker_label") or "A",
            text=text,
            start=start_ms / 1000,
            end=end_ms / 1000,
            is_final=bool(turn.get("end_of_turn")),
            turn_id=int(turn.get("turn_order") or 0),
        )

    async def send_audio(self, chunk: bytes) -> None:
        if self._ws is None:
            raise RuntimeError("RealAssemblyAIService.start() not called")
        await self._ws.send(chunk)

    async def segments(self) -> AsyncIterator[TranscriptSegment]:
        while True:
            segment = await self._queue.get()
            if segment is None:
                return
            yield segment

    async def stop(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "Terminate"}))
                if self._reader is not None:
                    await asyncio.wait_for(asyncio.shield(self._reader), timeout=5)
            except (TimeoutError, websockets.ConnectionClosed):
                pass
            finally:
                await self._ws.close()
                self._ws = None
