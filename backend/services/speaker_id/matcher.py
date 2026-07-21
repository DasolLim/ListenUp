"""Cosine matching of live audio against a user's saved voice profiles.

Rules (INTRODUCTION §5): never force a name below threshold, and when two
profiles are too close to call (within the ambiguity margin), stay generic —
a wrong name is worse than no name.
"""

import logging
import os
from dataclasses import dataclass, field

from services.speaker_id.base import cosine_similarity

logger = logging.getLogger("listenup.speaker_id.match")

# Real ECAPA gives same-voice cosine ~0.8+ and different-voice ~0.05, so 0.55
# keeps a wide safety margin while tolerating real-mic enroll-vs-runtime drift
# (noise, gain, echo cancellation). Tune per deployment via SPEAKER_MATCH_THRESHOLD.
DEFAULT_THRESHOLD = 0.55
DEFAULT_MARGIN = 0.05


def match_threshold() -> float:
    return float(os.environ.get("SPEAKER_MATCH_THRESHOLD", DEFAULT_THRESHOLD))


def match_margin() -> float:
    return float(os.environ.get("SPEAKER_MATCH_MARGIN", DEFAULT_MARGIN))


@dataclass
class Profile:
    profile_id: str
    display_name: str
    embeddings: list[list[float]] = field(default_factory=list)

    def similarity(self, embedding: list[float]) -> float:
        """Best cosine across the profile's samples — multiple enrollment/
        correction embeddings make altered voices (a cold, a bad mic) match."""
        return max(cosine_similarity(embedding, sample) for sample in self.embeddings)


@dataclass(frozen=True)
class Match:
    profile_id: str
    display_name: str
    similarity: float


class SpeakerMatcher:
    def __init__(
        self,
        profiles: list[Profile],
        threshold: float | None = None,
        margin: float | None = None,
    ) -> None:
        self.profiles = [p for p in profiles if p.embeddings]
        self.threshold = threshold if threshold is not None else match_threshold()
        self.margin = margin if margin is not None else match_margin()

    def match(self, embedding: list[float]) -> Match | None:
        if not self.profiles:
            return None
        scored = sorted(
            ((p.similarity(embedding), p) for p in self.profiles),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best = scored[0]

        # The ambiguity margin guards against confusing two DIFFERENT people.
        # Compare against the best profile with a different NAME, not just the
        # runner-up row — otherwise a duplicate/second enrollment of the same
        # person (same name, near-identical score) wrongly reads as ambiguous.
        rival = next((s for s, p in scored[1:] if p.display_name != best.display_name), None)
        logger.info(
            "speaker_match best=%s score=%.3f next_other=%s threshold=%.2f",
            best.display_name, best_score,
            f"{rival:.3f}" if rival is not None else "-",
            self.threshold,
        )
        if best_score < self.threshold:
            return None
        if rival is not None and best_score - rival < self.margin:
            # Two different enrolled people too close to call (overlap, similar voices).
            return None
        return Match(best.profile_id, best.display_name, best_score)
