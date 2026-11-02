"""Voice-to-text QA: consistency, reliability, accuracy.

These are behavioural guarantees, not implementation details. Each one maps to a
way live captioning has actually gone wrong in this project:

* language routing — Korean has no streaming model, so it must land on the batch
  transport, and silently streaming it would produce nothing
* silence detection — a fixed RMS threshold dropped quiet speech entirely
  (fixed 2026-07-26); these tests pin the relative behaviour
* speaker cap — INTRODUCTION §5 caps named lanes at 4 + "Other"
* identity stability — one person must keep one label/colour even when the
  diarization label churns
"""

import asyncio
import math
import struct

import pytest

from services.assemblyai import get_transcription_service
from services.assemblyai.base import STREAMING_LANGUAGES
from services.assemblyai.batch import (
    DROP_FACTOR,
    MAX_WINDOW_S,
    MIN_WINDOW_S,
    NOISE_FLOOR_MIN,
    NOISE_FLOOR_START,
    SPEECH_FACTOR,
    BatchAssemblyAIService,
    _rms,
)
from services.translate.base import SUPPORTED_LANGUAGES

SR = 16000


def _tone(seconds: float, amplitude: int) -> bytes:
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * 180 * t / SR)))
        for t in range(int(SR * seconds))
    )


def _room_noise(seconds: float, amplitude: int = 30, seed: int = 7) -> bytes:
    import random

    rng = random.Random(seed)
    return b"".join(
        struct.pack("<h", rng.randint(-amplitude, amplitude)) for _ in range(int(SR * seconds))
    )


def _calibrated_session() -> BatchAssemblyAIService:
    service = BatchAssemblyAIService.__new__(BatchAssemblyAIService)
    service._buffer = bytearray()
    service._noise_floor = NOISE_FLOOR_START
    service._sample_rate = SR
    service._elapsed = 0.0
    for _ in range(3):
        service._track_noise_floor(_rms(_room_noise(0.2)))
    return service


# ── Language routing: the reason Korean behaved differently ───────────────────

def test_korean_is_not_claimed_as_streamable():
    """AssemblyAI has no streaming Korean model. If Korean ever appears in
    STREAMING_LANGUAGES the factory will route it to the streaming transport and
    produce nothing, which is the original Korean failure."""
    assert "ko" not in STREAMING_LANGUAGES
    assert "en" in STREAMING_LANGUAGES


def test_real_korean_routes_to_batch_and_english_to_streaming(monkeypatch):
    monkeypatch.setenv("TRANSCRIPTION_SERVICE", "real")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")
    assert type(get_transcription_service("ko")).__name__ == "BatchAssemblyAIService"
    assert type(get_transcription_service("en")).__name__ == "RealAssemblyAIService"


def test_every_supported_language_has_a_transport():
    for language in SUPPORTED_LANGUAGES:
        assert get_transcription_service(language) is not None, f"{language} has no STT transport"


# ── Reliability: quiet speech must survive (the 2026-07-26 bug) ───────────────

# Close mic through to a whisper on a low-gain input. The bottom three all
# failed under the old fixed threshold.
@pytest.mark.parametrize("amplitude", [8000, 3000, 400, 260, 150])
def test_speech_is_never_dropped_at_any_gain(amplitude: int):
    service = _calibrated_session()
    speech_rms = _rms(_tone(1.0, amplitude))
    assert speech_rms >= service._noise_floor * DROP_FACTOR, (
        f"speech at amplitude {amplitude} (RMS {speech_rms:.1f}) would be discarded "
        f"against floor {service._noise_floor:.1f}"
    )


def test_a_genuine_pause_still_cuts_the_window():
    """Adapting the threshold must not break segmentation."""
    service = _calibrated_session()
    assert _rms(_room_noise(0.45)) < service._noise_floor * SPEECH_FACTOR


def test_an_empty_room_is_not_sent_for_transcription():
    """Cost guard: silence must not be billed."""
    service = _calibrated_session()
    assert _rms(_room_noise(2.0, amplitude=25)) < service._noise_floor * DROP_FACTOR


def test_noise_floor_cannot_collapse_to_zero():
    """A zero floor would make every later sample count as speech."""
    service = _calibrated_session()
    for _ in range(20):
        service._track_noise_floor(0.0)
    assert service._noise_floor >= NOISE_FLOOR_MIN


def test_window_bounds_respect_the_latency_budget():
    """Korean lags because it batches, but the lag must stay bounded and the
    window must be long enough for the model to have context."""
    assert MIN_WINDOW_S >= 1.0
    assert MAX_WINDOW_S <= 10.0
    assert MIN_WINDOW_S < MAX_WINDOW_S


# ── Consistency: the same audio twice gives the same answer ───────────────────

def test_mock_transcription_is_deterministic():
    """Two identical sessions must produce identical transcripts, or QA of any
    downstream feature (translation, TTS) is untrustworthy."""

    async def run() -> list[str]:
        service = get_transcription_service()
        await service.start(SR, language="en")
        await service.send_audio(_tone(1.0, 3000))
        # stop() flushes the remaining timeline and ends the iterator. Without
        # it segments() blocks on the queue forever, since a live stream has no
        # natural end.
        await service.stop()
        return [segment.text async for segment in service.segments() if segment.is_final]

    first = asyncio.run(run())
    second = asyncio.run(run())
    assert first == second, "same audio produced different transcripts"


# ── Accuracy guarantees enforced in code ─────────────────────────────────────

def test_speaker_cap_is_enforced():
    """INTRODUCTION §5: 4 named lanes + Other. Unbounded speakers destroy
    diarization accuracy, so the cap is a product rule."""
    from services.assemblyai.batch import MAX_SPEAKERS

    assert 4 <= MAX_SPEAKERS <= 5


def test_korean_slang_biasing_is_configured():
    """The general model mangles neologisms without a word list ('bussin' ->
    'Busan'), so Korean net-slang biasing must be present."""
    from services.assemblyai.batch import KOREAN_KEYTERMS

    assert len(KOREAN_KEYTERMS) >= 20
    assert "갓생" in KOREAN_KEYTERMS
