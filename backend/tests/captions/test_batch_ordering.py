"""Korean captions must arrive in the order they were spoken.

Windows on the batch transport are transcribed concurrently, and a short window
finishes long before a long one submitted earlier. That made emission order
completion order: a 0.16 s tail fragment beat the 2.7 s sentence it belonged to,
and the caption log rendered the end of the sentence before its beginning.

Out-of-order captions are bad in any transcript and worse in this one — someone
reading captions to follow a conversation has no audio to correct the order
against. These tests drive the failure deterministically by making the *later*
window resolve first.
"""

import asyncio

import pytest

from services.assemblyai.base import TranscriptSegment
from services.assemblyai.batch import BatchAssemblyAIService


def _segment(text: str, start: float) -> TranscriptSegment:
    return TranscriptSegment(
        speaker="A", text=text, start=start, end=start + 0.5, is_final=True, turn_id=1
    )


class _OrderedService(BatchAssemblyAIService):
    """Real windowing, scripted transcription with controllable latency."""

    def __init__(self, script: list[tuple[float, str]]) -> None:
        super().__init__(api_key="test-key")
        self._script = script
        self._call = 0

    async def _request(self, pcm: bytes, offset: float):  # noqa: ARG002
        delay, text = self._script[min(self._call, len(self._script) - 1)]
        index = self._call
        self._call += 1
        await asyncio.sleep(delay)
        return [_segment(text, float(index))]


# One second of loud audio. Windows are cut here by calling `_flush` directly
# rather than by feeding audio and waiting for the silence detector: windowing
# has its own tests (test_batch_silence.py), and driving it from audio would
# make these tests depend on VAD tuning rather than on emission order.
LOUD = b"\x00\x40" * 16000


def _window(service: BatchAssemblyAIService) -> None:
    service._buffer.extend(LOUD)  # noqa: SLF001 — exercising one window at a time
    service._flush()  # noqa: SLF001


async def _collect(service: BatchAssemblyAIService) -> list[TranscriptSegment]:
    out: list[TranscriptSegment] = []

    async def reader() -> None:
        async for segment in service.segments():
            out.append(segment)

    task = asyncio.create_task(reader())
    await service.stop()
    await asyncio.wait_for(task, timeout=5)
    return out


def test_a_slow_first_window_still_comes_first():
    """The exact shape of the bug: window 1 takes 300 ms, window 2 takes 10 ms."""

    async def run():
        service = _OrderedService([(0.30, "first"), (0.01, "second")])
        await service.start(sample_rate=16000, encoding="pcm_s16le", language="ko")
        _window(service)
        _window(service)
        return await _collect(service)

    segments = asyncio.run(run())
    assert [s.text for s in segments] == ["first", "second"], (
        "a window that finished sooner overtook an earlier one"
    )


def test_segments_are_monotonic_across_many_windows():
    """Randomised latencies: whatever order the API answers in, the transcript
    must read in the order it was spoken."""

    async def run():
        delays = [0.05, 0.001, 0.03, 0.002, 0.04, 0.001]
        service = _OrderedService([(d, f"w{i}") for i, d in enumerate(delays)])
        await service.start(sample_rate=16000, encoding="pcm_s16le", language="ko")
        for _ in delays:
            _window(service)
        return await _collect(service)

    segments = asyncio.run(run())
    texts = [s.text for s in segments]
    assert texts == sorted(texts, key=lambda t: int(t[1:])), texts
    starts = [s.start for s in segments]
    assert starts == sorted(starts), f"timestamps went backwards: {starts}"


def test_a_failed_window_does_not_stall_the_ones_behind_it():
    """One window erroring must not silence the rest of the conversation."""

    class _Flaky(_OrderedService):
        async def _request(self, pcm, offset):  # noqa: ARG002
            index = self._call
            self._call += 1
            if index == 0:
                raise ValueError("upstream blew up")
            return [_segment(f"w{index}", float(index))]

    async def run():
        service = _Flaky([(0, "")])
        await service.start(sample_rate=16000, encoding="pcm_s16le", language="ko")
        _window(service)
        _window(service)
        return await _collect(service)

    segments = asyncio.run(run())
    assert [s.text for s in segments] == ["w1"]


def test_stop_waits_for_the_last_window():
    """`stop` used to gather the jobs; the drainer is what actually queues
    segments, so waiting on the wrong thing would close the socket with the
    final window transcribed and never sent."""

    async def run():
        service = _OrderedService([(0.05, "only")])
        await service.start(sample_rate=16000, encoding="pcm_s16le", language="ko")
        _window(service)
        return await _collect(service)

    assert [s.text for s in asyncio.run(run())] == ["only"]


@pytest.mark.parametrize("windows", [1, 2, 5])
def test_every_window_is_emitted_exactly_once(windows):
    async def run():
        service = _OrderedService([(0.01, f"w{i}") for i in range(windows)])
        await service.start(sample_rate=16000, encoding="pcm_s16le", language="ko")
        for _ in range(windows):
            _window(service)
        return await _collect(service)

    segments = asyncio.run(run())
    assert len(segments) == windows
    assert len({s.text for s in segments}) == windows
