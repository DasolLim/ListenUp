"""Pausing must cut the Korean utterance window, not hold it open.

Korean has no streaming model, so audio is buffered into utterance windows and
cut on a pause in the *speech*. A pause in the *session* is invisible to that
logic: nothing arrives, `_should_flush` is never consulted, and the half-filled
buffer waits. Whatever is said after the user resumes then lands in the same
window and is transcribed as one continuous utterance, however long the gap.

That is a worse failure than it sounds. The reader is using captions because
they cannot hear the original, so they have no way to notice that two moments
minutes apart have been printed as one sentence. English never showed this — it
streams, and there is no local buffer to strand.
"""

import asyncio
import math
import struct

import pytest

from services.assemblyai.base import BYTES_PER_SECOND, TranscriptSegment
from services.assemblyai.batch import MIN_WINDOW_S, BatchAssemblyAIService

SR = 16000


def _tone(seconds: float, amplitude: int = 8000) -> bytes:
    """Continuous loud audio: never triggers a pause-cut on its own, so any
    boundary in the output came from an explicit flush and nothing else."""
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * 180 * t / SR)))
        for t in range(int(SR * seconds))
    )


CHUNK = _tone(0.2)  # one client frame


class _RecordingService(BatchAssemblyAIService):
    """Real windowing; records the windows that would have been transcribed."""

    def __init__(self) -> None:
        super().__init__(api_key="test-key")
        self._language = "ko"
        self.windows: list[float] = []

    async def _request(self, pcm: bytes, offset: float):
        self.windows.append(round(len(pcm) / BYTES_PER_SECOND, 3))
        return [
            TranscriptSegment(
                speaker="A", text="x", start=offset, end=offset + 0.1, is_final=True, turn_id=0
            )
        ]


async def _speak(service: BatchAssemblyAIService, seconds: float) -> None:
    """Feed audio in 200 ms frames, the way the client sends it."""
    for _ in range(round(seconds / 0.2)):
        await service.send_audio(CHUNK)


async def _started() -> _RecordingService:
    service = _RecordingService()
    await service.start(sample_rate=SR, encoding="pcm_s16le", language="ko")
    return service


def test_pausing_closes_the_open_window():
    """The half-finished utterance is submitted at the pause, not held."""

    async def run():
        service = await _started()
        await _speak(service, 1.0)  # under MIN_WINDOW_S, so nothing is cut yet
        before = list(service.windows)
        await service.flush()
        return before, service.windows

    before, after = asyncio.run(run())
    assert before == [], "nothing should have been submitted yet"
    assert len(after) == 1
    assert after[0] == pytest.approx(1.0, abs=0.05)


def test_speech_after_a_pause_is_not_glued_to_speech_before_it():
    """The defect, driven end to end: two utterances either side of a pause."""

    async def run():
        service = await _started()
        await _speak(service, 1.0)
        await service.flush()  # the user pauses here
        await _speak(service, 1.0)
        await service.stop()
        return service.windows

    windows = asyncio.run(run())
    assert len(windows) == 2, f"expected two windows, got {windows}"
    assert all(w == pytest.approx(1.0, abs=0.05) for w in windows)


def test_without_the_flush_the_two_utterances_become_one():
    """The same session with no flush, pinning what the fix prevents.

    If this ever stops merging, the flush is no longer load-bearing and the test
    above would be passing for the wrong reason.
    """

    async def run():
        service = await _started()
        await _speak(service, 1.0)
        await _speak(service, 1.0)
        await service.stop()
        return service.windows

    assert asyncio.run(run()) == [pytest.approx(2.0, abs=0.05)], "expected one merged window"


def test_flushing_an_empty_buffer_does_nothing():
    """Pausing twice, or before speaking at all, must not submit empty audio —
    every window submitted is a billable API call."""

    async def run():
        service = await _started()
        await service.flush()
        await service.flush()
        return service.windows

    assert asyncio.run(run()) == []


def test_the_audio_timeline_continues_across_the_pause():
    """Timestamps are positions in the audio, not on the wall clock, so the
    window after a pause starts where the one before it ended rather than
    jumping forward by the length of the pause."""

    async def run():
        service = await _started()
        await _speak(service, 1.0)
        await service.flush()
        first = service._elapsed
        await _speak(service, 1.0)
        await service.flush()
        return first, service._elapsed

    first, second = asyncio.run(run())
    assert first == pytest.approx(1.0, abs=0.05)
    assert second == pytest.approx(2.0, abs=0.05)


def test_the_flush_adds_a_boundary_without_losing_audio():
    """It is an extra cut, not a replacement for the windower: everything
    spoken is still accounted for exactly once."""

    async def run():
        service = await _started()
        await _speak(service, MIN_WINDOW_S + 0.4)
        await service.flush()
        return service.windows

    windows = asyncio.run(run())
    assert windows
    assert sum(windows) == pytest.approx(MIN_WINDOW_S + 0.4, abs=0.1)


def test_streaming_transports_ignore_the_flush():
    """`flush` is concrete on the base class so the socket can call it
    unconditionally: a streaming transport has already sent every byte, so it
    must neither raise nor end the session."""

    async def run():
        from services.assemblyai.mock import MockTranscriptionService

        service = MockTranscriptionService("family")
        await service.start(sample_rate=SR)
        await service.flush()
        await service.send_audio(CHUNK)

    asyncio.run(run())
