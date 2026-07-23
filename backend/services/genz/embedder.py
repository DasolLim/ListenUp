"""Text embedders for slang retrieval.

Default = HashingTextEmbedder: a deterministic char-n-gram + word hashing
vectorizer. No model download, no network, no per-call cost, and stable across
processes (so vectors stored in pgvector stay comparable). It captures lexical
similarity — which dominates slang lookup, where the query usually *contains*
the term or a close morphological variant ("rizz"/"rizzler", "bussin"/"bussing").

Optional real path (TEXT_EMBEDDER=real): sentence-transformers MiniLM for full
semantic recall, loaded once — used only if the package is installed.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from functools import lru_cache

from services.genz.base import EMBED_DIM, TextEmbedder

_WORD = re.compile(r"[a-z0-9]+|[가-힣]+")  # latin/digit runs + Hangul syllables


def _tokens(text: str) -> list[str]:
    words = _WORD.findall(text.lower())
    grams: list[str] = []
    for w in words:
        grams.append(f"w:{w}")  # whole word — strongest signal
        padded = f"^{w}$"
        for i in range(len(padded) - 2):  # char trigrams for fuzzy/morphological recall
            grams.append(padded[i : i + 3])
    return grams


class HashingTextEmbedder(TextEmbedder):
    def load(self) -> None:  # nothing to warm
        return None

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * EMBED_DIM
        for tok in _tokens(text):
            h = hashlib.blake2b(tok.encode(), digest_size=8).digest()
            bucket = int.from_bytes(h[:4], "big") % EMBED_DIM
            sign = 1.0 if h[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]


class MiniLMTextEmbedder(TextEmbedder):
    """sentence-transformers all-MiniLM-L6-v2, projected/padded to EMBED_DIM.

    Opt-in and lazy: importing sentence-transformers is deferred to load() so the
    default install never needs it.
    """

    def __init__(self) -> None:
        self._model = None

    def load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]

        self._model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(self, text: str) -> list[float]:
        if self._model is None:
            self.load()
        assert self._model is not None
        raw = self._model.encode(text, normalize_embeddings=False).tolist()
        # Fit to EMBED_DIM (MiniLM is 384): truncate or zero-pad, then L2-normalize.
        vec = (raw[:EMBED_DIM] + [0.0] * EMBED_DIM)[:EMBED_DIM]
        norm = math.sqrt(sum(x * x for x in vec))
        return [x / norm for x in vec] if norm else vec


@lru_cache(maxsize=1)
def get_text_embedder() -> TextEmbedder:
    kind = os.environ.get("TEXT_EMBEDDER", "hashing").lower()
    embedder: TextEmbedder = (
        MiniLMTextEmbedder() if kind in ("real", "minilm") else HashingTextEmbedder()
    )
    embedder.load()
    return embedder
