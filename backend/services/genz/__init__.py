"""GenZ slang explainer service (Phase 5)."""

from services.genz.base import (
    EMBED_DIM,
    RetrievedTerm,
    SlangExplanation,
    SlangTerm,
    TextEmbedder,
)
from services.genz.embedder import get_text_embedder
from services.genz.kb import LocalSlangKB, get_slang_kb

__all__ = [
    "EMBED_DIM",
    "RetrievedTerm",
    "SlangExplanation",
    "SlangTerm",
    "TextEmbedder",
    "LocalSlangKB",
    "get_slang_kb",
    "get_text_embedder",
]
