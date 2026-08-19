"""Curation pipeline: turn logged gaps into KB entries a human has approved.

`slang_gap_log` records terms users hit that we could not confidently explain.
Nothing consumed it, so the corpus never grew — and no model update will grow it
for us, because the whole problem is coinage that postdates any training cutoff.
This module is the mechanism behind "stays current".

Two decisions shape everything here:

**Resolution is web-grounded.** Asking a model what a new term means is asking
the same memory that failed in the first place. OpenRouter's `:online` suffix
runs a web search and feeds the results to the model, so a term coined last
month can be resolved from what people actually wrote about it. That is
affordable *because* this is a batch job over a deduplicated backlog — the same
call per request would be indefensible on both latency and cost.

**Nothing goes live without a human.** This corpus feeds STT biasing, cultural
translation *and* explanations, so one wrong auto-ingested definition propagates
to all three at once, in a product whose users cannot hear the original to check
it against. Resolution writes to a pending queue; only `promote()` reaches the
KB. To make the approval real rather than a rubber stamp, every candidate
carries the `sources` the resolver actually used — approving means checking
them, and a candidate that cites nothing is visibly weaker than one that does.

Nothing in here may be imported from a request path; `scripts/curate_slang.py`
is the only entry point.
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from services.genz.base import SlangTerm
from services.genz.kb import LocalSlangKB, _norm, get_slang_kb

logger = logging.getLogger("listenup.genz.curation")

_DATA_DIR = Path(os.environ.get("GENZ_DATA_DIR", str(Path(__file__).parent / "data")))

# A gap this short is punctuation or a stray particle, not a coinage worth an
# API call; this long is a whole sentence the model quoted rather than a term.
MIN_TERM_CHARS = 1
MAX_TERM_CHARS = 40

PENDING, PROMOTED, REJECTED = "pending", "promoted", "rejected"


@dataclass(frozen=True)
class Candidate:
    """A resolved gap awaiting a human decision."""

    term: str
    meaning: str = ""
    origin: str = ""
    region: str = ""
    first_seen: str = ""
    example: str = ""
    adult_friendly_explanation: str = ""
    # False when the resolver judged this not to be slang at all (a typo, a
    # proper noun, transcription noise). Auto-rejected rather than queued: a
    # review queue full of junk is a queue nobody reads, which is the same as
    # having no approval step.
    is_slang: bool = True
    # Where the definition came from. An approver needs these to check the claim;
    # a candidate citing nothing is visibly weaker than one that does.
    sources: list[str] = field(default_factory=list)
    resolver: str = ""
    status: str = PENDING
    note: str = ""
    seen: int = 1
    at: str = ""

    def to_term(self) -> SlangTerm:
        return SlangTerm(
            term=self.term,
            meaning=self.meaning,
            origin=self.origin,
            region=self.region,
            first_seen=self.first_seen,
            example=self.example,
            adult_friendly_explanation=self.adult_friendly_explanation,
        )


class SlangResolver(ABC):
    """Given a term, produce a candidate definition. Never raises: one
    unresolvable term must not end the batch."""

    name = "base"

    @abstractmethod
    async def resolve(self, term: str, seen: int) -> Candidate: ...


class MockSlangResolver(SlangResolver):
    """Deterministic, free, no network — the default, so the whole pipeline can
    be developed and tested without spending credits (INTRODUCTION §6).

    It mimics the one judgement that matters structurally: strings that don't
    look like slang are marked `is_slang=False` so the auto-reject path is
    exercised in tests rather than only in production.
    """

    name = "mock"

    async def resolve(self, term: str, seen: int) -> Candidate:
        plausible = bool(re.fullmatch(r"[\w가-힣ㄱ-ㅎㅏ-ㅣ'’\- ]{1,40}", term)) and (
            len(term.split()) <= 4
        )
        if not plausible:
            return Candidate(
                term=term, is_slang=False, resolver=self.name, seen=seen,
                note="does not look like a term",
            )
        return Candidate(
            term=term,
            meaning=f"[mock] a slang sense of {term!r}",
            origin="[mock] resolved without a network call",
            region="unknown",
            example=f"[mock] example using {term}",
            adult_friendly_explanation=f"[mock] plain-language gloss of {term}",
            sources=["https://example.invalid/mock"],
            resolver=self.name,
            seen=seen,
        )


RESOLVE_PROMPT = """You are a lexicographer documenting current slang for a \
translation product. You will be given ONE term that our dictionary could not \
explain. Use the web results available to you; prefer recent, first-hand usage \
(social posts, dictionaries of record, reporting) over your own recollection.

Return ONLY this JSON, no prose and no code fences:
{"is_slang": true|false,
 "term": "<the term, normalised>",
 "meaning": "<one plain sentence>",
 "origin": "<where it came from>",
 "region": "<en / ko / both / a community>",
 "first_seen": "<year or month it appeared, or empty>",
 "example": "<one natural sentence using it>",
 "adult_friendly_explanation": "<how to explain it to someone unfamiliar>",
 "sources": ["<url>", "..."]}

Set "is_slang": false for a typo, a proper noun, an ordinary word, or \
transcription noise, and leave the other fields empty. Do not guess: if the web \
results do not actually establish a meaning, say so by setting "is_slang" false \
with the meaning left empty. A confident wrong definition is worse than none — \
it will be shown to people who cannot hear the original to check it."""


class OpenRouterSlangResolver(SlangResolver):
    """Web-grounded resolution via OpenRouter's `:online` suffix.

    The suffix is what makes this worth doing: the plain model shares the exact
    blind spot that put the term in the gap log.
    """

    name = "openrouter-online"

    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        base = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o")
        self.model = base if base.endswith(":online") else f"{base}:online"

    async def resolve(self, term: str, seen: int) -> Candidate:
        import httpx

        from services.openrouter.base import parse_llm_json

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "HTTP-Referer": "https://listenup.app",
                        "X-Title": "ListenUp",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": RESOLVE_PROMPT},
                            {"role": "user", "content": term},
                        ],
                        "temperature": 0.2,
                    },
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.warning("slang_resolve_failed term=%r error=%s", term, exc)
            return Candidate(term=term, is_slang=False, resolver=self.name,
                             seen=seen, note=f"resolver error: {exc}")

        parsed = parse_llm_json(content) or {}
        if not parsed.get("is_slang") or not str(parsed.get("meaning") or "").strip():
            return Candidate(term=term, is_slang=False, resolver=self.name, seen=seen,
                             note="resolver found no established meaning")
        sources = [str(s) for s in (parsed.get("sources") or []) if str(s).strip()]
        return Candidate(
            term=str(parsed.get("term") or term).strip(),
            meaning=str(parsed["meaning"]).strip(),
            origin=str(parsed.get("origin") or ""),
            region=str(parsed.get("region") or ""),
            first_seen=str(parsed.get("first_seen") or ""),
            example=str(parsed.get("example") or ""),
            adult_friendly_explanation=str(parsed.get("adult_friendly_explanation") or ""),
            sources=sources,
            resolver=self.name,
            seen=seen,
        )


def get_slang_resolver() -> SlangResolver:
    """Mock by default. The real resolver costs money and is only ever reached
    from the batch script, never from a request."""
    if os.environ.get("SLANG_RESOLVER_SERVICE", "mock").lower() == "real":
        return OpenRouterSlangResolver()
    return MockSlangResolver()


class PendingStore:
    """The review queue: one JSON line per candidate, keyed by normalised term.

    A flat file matches how the local KB already stores curation state, and the
    queue is human-scale by construction — it only ever holds terms real users
    hit that we could not explain.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._dir = data_dir or _DATA_DIR
        self._path = self._dir / "pending_terms.jsonl"

    def _read(self) -> dict[str, Candidate]:
        if not self._path.exists():
            return {}
        rows: dict[str, Candidate] = {}
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a truncated write must not brick the queue
                known = {f for f in Candidate.__annotations__}
                rows[_norm(data.get("term", ""))] = Candidate(
                    **{k: v for k, v in data.items() if k in known}
                )
        return rows

    def _write(self, rows: dict[str, Candidate]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for candidate in rows.values():
                fh.write(json.dumps(asdict(candidate), ensure_ascii=False) + "\n")
        tmp.replace(self._path)  # atomic: a crash mid-write can't lose the queue

    def all(self) -> list[Candidate]:
        return list(self._read().values())

    def by_status(self, status: str) -> list[Candidate]:
        return [c for c in self._read().values() if c.status == status]

    def get(self, term: str) -> Candidate | None:
        return self._read().get(_norm(term))

    def upsert(self, candidate: Candidate) -> None:
        rows = self._read()
        rows[_norm(candidate.term)] = candidate
        self._write(rows)

    def set_status(self, term: str, status: str, note: str = "") -> Candidate | None:
        rows = self._read()
        key = _norm(term)
        if key not in rows:
            return None
        from dataclasses import replace

        updated = replace(rows[key], status=status, note=note or rows[key].note)
        rows[key] = updated
        self._write(rows)
        return updated


def _gap_counts(kb: LocalSlangKB, limit: int) -> dict[str, int]:
    """Distinct gap terms and how often they were hit, most-wanted first."""
    counts: dict[str, int] = {}
    for row in kb.gaps(limit=limit):
        term = (row.get("query") or "").strip()
        if MIN_TERM_CHARS <= len(term) <= MAX_TERM_CHARS:
            counts[term] = counts.get(term, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


async def resolve_gaps(
    *,
    kb: LocalSlangKB | None = None,
    store: PendingStore | None = None,
    resolver: SlangResolver | None = None,
    limit: int = 500,
    max_terms: int = 25,
    min_seen: int = 1,
) -> dict[str, int]:
    """Read the gap log, resolve what is new, and queue it for review.

    Skips, in order, anything the KB already covers (the log accumulates terms
    that were later added, and historically also terms that a since-fixed
    matching bug reported as missing), then anything already decided — including
    rejections, so a term a human rejected does not return every run.

    Returns counts, never raises: this runs unattended.
    """
    kb = kb or get_slang_kb()
    store = store or PendingStore()
    resolver = resolver or get_slang_resolver()

    known = {_norm(t.term) for t in kb.all_terms()}
    decided = set(store._read())  # noqa: SLF001 — same module's storage
    stats = dict(seen=0, already_known=0, already_decided=0, resolved=0, auto_rejected=0)

    for term, count in _gap_counts(kb, limit).items():
        stats["seen"] += 1
        if count < min_seen:
            continue
        key = _norm(term)
        if key in known:
            stats["already_known"] += 1
            continue
        if key in decided:
            stats["already_decided"] += 1
            continue
        if stats["resolved"] + stats["auto_rejected"] >= max_terms:
            break
        candidate = await resolver.resolve(term, count)
        if not candidate.is_slang:
            store.upsert(
                Candidate(
                    **{**asdict(candidate), "status": REJECTED,
                       "at": datetime.now(UTC).isoformat(),
                       "note": candidate.note or "auto-rejected: not a term"}
                )
            )
            stats["auto_rejected"] += 1
            continue
        store.upsert(
            Candidate(**{**asdict(candidate), "status": PENDING,
                         "at": datetime.now(UTC).isoformat()})
        )
        stats["resolved"] += 1
        logger.info("slang_candidate_queued term=%r seen=%d", candidate.term, count)
    return stats


def promote(term: str, *, kb: LocalSlangKB | None = None,
            store: PendingStore | None = None) -> SlangTerm | None:
    """Move an approved candidate into the live KB.

    Idempotent in both senses. Retrieval was already safe — `add_term` upserts
    on the normalised term and `_load` keeps the last row — but the backing CSV
    is append-only, so re-promoting used to add a row that only the loader's
    dedupe hid. A term already live is left alone; a term marked promoted whose
    KB entry has gone missing is re-added, which makes this usable to re-sync.
    """
    kb = kb or get_slang_kb()
    store = store or PendingStore()
    candidate = store.get(term)
    if candidate is None or candidate.status == REJECTED:
        return None
    if candidate.status == PROMOTED and _norm(candidate.term) in {
        _norm(t.term) for t in kb.all_terms()
    }:
        return candidate.to_term()  # already live; nothing to write
    kb.add_term(candidate.to_term())
    store.set_status(candidate.term, PROMOTED)
    logger.info("slang_term_promoted term=%r", candidate.term)
    return candidate.to_term()


def reject(term: str, note: str = "", *, store: PendingStore | None = None) -> bool:
    store = store or PendingStore()
    return store.set_status(term, REJECTED, note or "rejected by curator") is not None
