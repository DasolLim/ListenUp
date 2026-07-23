"""Mock STT: canned diarized segments, paced by the audio actually streamed in.

Develops/tests the whole caption pipeline with zero API spend. Each fixture
final segment is preceded by two interim (is_final=False) drafts, released as
the received audio duration crosses the segment's timeline — so the mock
behaves like a live provider, not an instant dump.
"""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

from services.assemblyai.base import (
    BYTES_PER_SECOND,
    TranscriptionService,
    TranscriptSegment,
    assert_audio_format,
    assert_spoken_language,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
_SENTINEL: TranscriptSegment | None = None


def _interims(final: TranscriptSegment) -> list[TranscriptSegment]:
    words = final.text.split()
    drafts = []
    for fraction in (0.4, 0.75):
        count = max(1, int(len(words) * fraction))
        if count < len(words):
            span = final.start + (final.end - final.start) * fraction
            drafts.append(
                TranscriptSegment(
                    speaker=final.speaker,
                    text=" ".join(words[:count]),
                    start=final.start,
                    end=span,
                    is_final=False,
                    turn_id=final.turn_id,
                )
            )
    return drafts


class MockTranscriptionService(TranscriptionService):
    def __init__(self, fixture: str | None = None) -> None:
        name = fixture or os.environ.get("MOCK_FIXTURE", "family")
        raw = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
        finals = [
            TranscriptSegment(**item, is_final=True, turn_id=i) for i, item in enumerate(raw)
        ]
        self._timeline: list[TranscriptSegment] = []
        for final in finals:
            self._timeline.extend(_interims(final))
            self._timeline.append(final)
        self._timeline.sort(key=lambda s: s.end)
        self._queue: asyncio.Queue[TranscriptSegment | None] = asyncio.Queue()
        self._audio_seconds = 0.0
        self._emitted = 0
        self._started = False

    async def start(
        self, sample_rate: int, encoding: str = "pcm_s16le", language: str = "en"
    ) -> None:
        assert_audio_format(sample_rate, encoding)
        assert_spoken_language(language)
        self._language = language
        self._started = True

    async def send_audio(self, chunk: bytes) -> None:
        if not self._started:
            raise RuntimeError("MockTranscriptionService.start() not called")
        self._audio_seconds += len(chunk) / BYTES_PER_SECOND
        while self._emitted < len(self._timeline):
            segment = self._timeline[self._emitted]
            if segment.end > self._audio_seconds:
                break
            self._emitted += 1
            await self._queue.put(segment)

    async def segments(self) -> AsyncIterator[TranscriptSegment]:
        while True:
            segment = await self._queue.get()
            if segment is None:
                return
            yield segment

    async def stop(self) -> None:
        # Flush anything the streamed audio nearly reached, then end the iterator.
        while self._emitted < len(self._timeline):
            segment = self._timeline[self._emitted]
            self._emitted += 1
            await self._queue.put(segment)
        await self._queue.put(_SENTINEL)
