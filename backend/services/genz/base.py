"""GenZ slang explainer — data models + text-embedding interface (Phase 5).

A curated slang knowledge base (KB) grounds an LLM explanation (RAG): retrieve
the closest terms by vector similarity, feed them as context, and return a
structured, adult-friendly explanation. Everything runs locally and free by
default (INTRODUCTION §6 cost awareness) — the embedder is a dependency-free
hashing vectorizer, mirroring the "local CPU, load once" ethos of speaker-ID.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field

# Dimension of the slang text embeddings (pgvector column is vector(256)).
EMBED_DIM = 256


@dataclass(frozen=True)
class SlangTerm:
    term: str
    meaning: str
    origin: str = ""
    region: str = ""
    first_seen: str = ""
    example: str = ""
    adult_friendly_explanation: str = ""

    def context_text(self) -> str:
        """The text embedded for retrieval — term dominates, with meaning/example
        for morphological and semantic recall."""
        return f"{self.term}. {self.meaning}. {self.example}".strip()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetrievedTerm:
    term: SlangTerm
    score: float  # cosine similarity in [-1, 1]


@dataclass(frozen=True)
class SlangExplanation:
    term: str
    plain_meaning: str
    origin: str = ""
    first_seen: str = ""
    region: str = ""
    example: str = ""
    adult_friendly_explanation: str = ""
    # "high" when grounded in a KB match; "low" when the LLM answered alone.
    confidence: str = "high"
    grounded_terms: list[str] = field(default_factory=list)
    cached: bool = False
    model: str = ""
    tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class TextEmbedder(ABC):
    """text → fixed-dim semantic-ish vector. Local + CPU + free by default."""

    @abstractmethod
    def load(self) -> None:
        """Warm any model/weights once — never per request."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Return an EMBED_DIM, L2-normalized vector."""
