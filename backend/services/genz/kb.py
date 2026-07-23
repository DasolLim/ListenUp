"""Slang knowledge base — retrieval, ingest, and gap logging.

Runtime backend is local by default: the curated seed CSV is loaded once, each
term embedded via the TextEmbedder, and lookups are cosine top-k with a lexical
bonus (the query usually contains the term itself). Ships fully local + free so
every Phase-5 gate runs without credentials; the production pgvector schema
lives in db/migrations/0002_slang_kb.sql and mirrors this interface.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import threading
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from services.genz.base import EMBED_DIM, RetrievedTerm, SlangTerm, cosine
from services.genz.embedder import get_text_embedder

logger = logging.getLogger("listenup.genz.kb")

_SEED = Path(__file__).parent / "seed" / "slang_seed.csv"
_DATA_DIR = Path(os.environ.get("GENZ_DATA_DIR", str(Path(__file__).parent / "data")))

# A whole-word term appearing in the query is a near-certain match; the bonus
# lifts exact/substring hits above fuzzy neighbours regardless of embedder.
LEXICAL_BONUS = 0.5
# Below this combined score the term is not considered relevant grounding.
RELEVANCE_FLOOR = 0.18


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


class LocalSlangKB:
    def __init__(
        self,
        seed_path: Path = _SEED,
        data_dir: Path = _DATA_DIR,
    ) -> None:
        self._seed_path = seed_path
        self._data_dir = data_dir
        self._added_path = data_dir / "added_terms.csv"
        self._gap_path = data_dir / "gap_log.jsonl"
        self._lock = threading.Lock()
        self._embedder = get_text_embedder()
        self._terms: list[SlangTerm] = []
        self._vectors: list[list[float]] = []
        self._load()

    def _load(self) -> None:
        # Seed first, then admin-added rows; later rows override by term name so
        # an ingested update (appended) wins over the seeded original.
        merged: dict[str, SlangTerm] = {}
        for path in (self._seed_path, self._added_path):
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if not (row.get("term") or "").strip():
                        continue
                    term = SlangTerm(**{k: (row.get(k) or "") for k in SlangTerm.__annotations__})
                    merged[_norm(term.term)] = term
        self._terms = list(merged.values())
        self._vectors = [self._embedder.embed(t.context_text()) for t in self._terms]
        logger.info("genz_kb_loaded terms=%d dim=%d", len(self._terms), EMBED_DIM)

    def all_terms(self) -> list[SlangTerm]:
        return list(self._terms)

    def search(self, query: str, k: int = 3) -> list[RetrievedTerm]:
        """Top-k relevant terms (combined cosine + lexical bonus), above the floor."""
        if not query.strip():
            return []
        qvec = self._embedder.embed(query)
        qnorm = _norm(query)
        scored: list[RetrievedTerm] = []
        for term, vec in zip(self._terms, self._vectors, strict=True):
            score = cosine(qvec, vec)
            tnorm = _norm(term.term)
            if tnorm and (tnorm in qnorm or qnorm in tnorm):
                score = min(1.0, score + LEXICAL_BONUS)
            if score >= RELEVANCE_FLOOR:
                scored.append(RetrievedTerm(term=term, score=round(score, 4)))
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:k]

    def add_term(self, term: SlangTerm) -> bool:
        """Add or update a term; immediately retrievable. Returns True if it was
        newly created, False if it updated an existing term."""
        with self._lock:
            key = _norm(term.term)
            vec = self._embedder.embed(term.context_text())
            self._data_dir.mkdir(parents=True, exist_ok=True)
            new_file = not self._added_path.exists()
            with self._added_path.open("a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(SlangTerm.__annotations__))
                if new_file:
                    writer.writeheader()
                writer.writerow(term.to_dict())
            # Update in place if present (last-write-wins), else append.
            idx = next((i for i, t in enumerate(self._terms) if _norm(t.term) == key), None)
            if idx is None:
                self._terms.append(term)
                self._vectors.append(vec)
                created = True
            else:
                self._terms[idx] = term
                self._vectors[idx] = vec
                created = False
            logger.info("genz_kb_ingest term=%r created=%s", term.term, created)
            return created

    def log_gap(self, query: str) -> None:
        """Record a searched term that had no confident KB match (curation signal)."""
        with self._lock:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            with self._gap_path.open("a", encoding="utf-8") as fh:
                fh.write(
                    json.dumps(
                        {"query": query.strip(), "at": datetime.now(UTC).isoformat()},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def gaps(self, limit: int = 100) -> list[dict]:
        if not self._gap_path.exists():
            return []
        with self._gap_path.open(encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        return rows[-limit:][::-1]


@lru_cache(maxsize=1)
def get_slang_kb() -> LocalSlangKB:
    return LocalSlangKB()
