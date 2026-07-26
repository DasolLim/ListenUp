"""Korean batch STT: silence detection must be relative to the noise floor.

Regression guard for the Korean-caption inconsistency. A fixed int16 RMS
threshold (the previous `SILENCE_RMS = 320.0`) is gain-dependent: quiet-but-real
speech was classed as silence, so windows were cut mid-sentence, and low-gain
audio had whole windows discarded and never transcribed. English is unaffected
because it uses the streaming transport with its own VAD, which is why only
Korean looked unreliable.
"""

import math
import random
import struct

from services.assemblyai.batch import (
    DROP_FACTOR,
    NOISE_FLOOR_MIN,
    NOISE_FLOOR_START,
    SPEECH_FACTOR,
    BatchAssemblyAIService,
    _rms,
)

SR = 16000


def _tone(seconds: float, amplitude: int) -> bytes:
    return b"".join(
        struct.pack("<h", int(amplitude * math.sin(2 * math.pi * 180 * t / SR)))
        for t in range(int(SR * seconds))
    )


def _room_noise(seconds: float, amplitude: int = 30) -> bytes:
    rng = random.Random(1234)
    return b"".join(
        struct.pack("<h", rng.randint(-amplitude, amplitude)) for _ in range(int(SR * seconds))
    )


def _session() -> BatchAssemblyAIService:
    """A service instance without the API-key requirement of __init__."""
    service = BatchAssemblyAIService.__new__(BatchAssemblyAIService)
    service._buffer = bytearray()
    service._noise_floor = NOISE_FLOOR_START
    service._sample_rate = SR
    service._elapsed = 0.0
    return service


def _calibrated() -> BatchAssemblyAIService:
    service = _session()
    for _ in range(3):
        service._track_noise_floor(_rms(_room_noise(0.2)))
    return service


# Amplitudes spanning a close mic down to a whisper on a low-gain input. The
# bottom three all failed under the old fixed threshold.
SPEECH_AMPLITUDES = [8000, 3000, 400, 260, 150]


def test_speech_survives_at_every_gain_level():
    for amplitude in SPEECH_AMPLITUDES:
        service = _calibrated()
        speech_rms = _rms(_tone(1.0, amplitude))
        assert speech_rms >= service._noise_floor * DROP_FACTOR, (
            f"speech at amplitude {amplitude} (RMS {speech_rms:.1f}) would be dropped "
            f"against floor {service._noise_floor:.1f}"
        )


def test_pause_still_cuts_the_window():
    """Adapting must not break segmentation: a genuine pause still flushes."""
    service = _calibrated()
    pause_rms = _rms(_room_noise(0.45))
    assert pause_rms < service._noise_floor * SPEECH_FACTOR


def test_noise_floor_adapts_down_to_a_quiet_room():
    service = _session()
    assert service._noise_floor == NOISE_FLOOR_START
    for _ in range(5):
        service._track_noise_floor(_rms(_room_noise(0.2, amplitude=20)))
    assert service._noise_floor < NOISE_FLOOR_START
    assert service._noise_floor >= NOISE_FLOOR_MIN


def test_noise_floor_never_collapses_to_zero():
    """Digital silence must not pin the floor at 0, which would make every
    subsequent sample count as speech."""
    service = _session()
    for _ in range(10):
        service._track_noise_floor(0.0)
    assert service._noise_floor >= NOISE_FLOOR_MIN


def test_pure_silence_window_is_still_dropped():
    """Cost guard: an empty room must not be sent for transcription."""
    service = _calibrated()
    silence_rms = _rms(_room_noise(2.0, amplitude=25))
    assert silence_rms < service._noise_floor * DROP_FACTOR
