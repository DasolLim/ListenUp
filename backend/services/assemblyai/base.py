"""Single STT interface (INTRODUCTION §5: one provider, one module, swappable mock)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

# AssemblyAI Universal-Streaming requires mono 16-bit PCM.
REQUIRED_SAMPLE_RATE = 16000
REQUIRED_ENCODING = "pcm_s16le"
BYTES_PER_SECOND = REQUIRED_SAMPLE_RATE * 2  # mono s16le


class AudioFormatError(ValueError):
    """Raised when the client audio format is not 16 kHz mono s16le PCM."""


def assert_audio_format(sample_rate: int, encoding: str) -> None:
    if sample_rate != REQUIRED_SAMPLE_RATE or encoding != REQUIRED_ENCODING:
        raise AudioFormatError(
            f"Unsupported audio format: {sample_rate} Hz/{encoding}. "
            f"Transcription requires {REQUIRED_SAMPLE_RATE} Hz mono {REQUIRED_ENCODING} "
            "(16-bit little-endian PCM). Resample/re-encode before streaming."
        )


@dataclass(frozen=True)
class TranscriptSegment:
    speaker: str  # provider label ("A", "B", …) — names arrive in Phase 3
    text: str
    start: float  # seconds from session start
    end: float
    is_final: bool
    # Stable per-turn id (AssemblyAI turn_order). Interim and final versions of
    # the same utterance share it — the UI keys bubbles on this, because the
    # speaker label and timestamps can be revised between interim and final.
    turn_id: int = 0


class TranscriptionService(ABC):
    """Start once, feed PCM chunks, consume diarized segments, stop."""

    @abstractmethod
    async def start(self, sample_rate: int, encoding: str = REQUIRED_ENCODING) -> None: ...

    @abstractmethod
    async def send_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    def segments(self) -> AsyncIterator[TranscriptSegment]: ...

    @abstractmethod
    async def stop(self) -> None: ...
