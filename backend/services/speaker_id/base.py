"""Speaker-ID embedding interface (INTRODUCTION §4: ECAPA-TDNN, CPU, local).

Answers "which real person is this?" — AssemblyAI's diarization answers
"who spoke when". They run together, not as competitors.
"""

import math
from abc import ABC, abstractmethod

from services.assemblyai.base import BYTES_PER_SECOND, assert_audio_format

EMBEDDING_DIM = 192
# Enrollment needs 20–30 s of speech (INTRODUCTION §2); runtime matching uses
# shorter windows, so the floor lives here and routes decide which to apply.
MIN_ENROLL_SECONDS = 20.0
MIN_MATCH_SECONDS = 2.0


def audio_seconds(pcm: bytes) -> float:
    return len(pcm) / BYTES_PER_SECOND


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class SpeakerEmbedder(ABC):
    """audio (16 kHz mono s16le PCM) → 192-dim voice embedding."""

    @abstractmethod
    def load(self) -> None:
        """Load model weights once at startup — never per request."""

    @abstractmethod
    def embed(self, pcm: bytes, sample_rate: int = 16000) -> list[float]: ...

    def validate(self, pcm: bytes, sample_rate: int, min_seconds: float) -> None:
        assert_audio_format(sample_rate, "pcm_s16le")
        seconds = audio_seconds(pcm)
        if seconds < min_seconds:
            raise ValueError(
                f"Audio too short: {seconds:.1f}s of speech, need at least {min_seconds:.0f}s."
            )
