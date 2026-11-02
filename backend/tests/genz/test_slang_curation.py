"""The currency loop: gap log → reviewed candidate → live KB entry.

The acceptance the design turns on is that resolution and promotion are separate
steps. This corpus feeds STT biasing, cultural translation and explanations at
once, and its readers are people who cannot hear the original to check a wrong
definition against — so "the job ran" must never mean "the term is live".
"""

import asyncio
import json

import pytest

from services.genz.base import SlangTerm
from services.genz.curation import (
    PENDING,
    PROMOTED,
    REJECTED,
    Candidate,
    MockSlangResolver,
    PendingStore,
    SlangResolver,
    promote,
    reject,
    resolve_gaps,
)
from services.genz.kb import LocalSlangKB


@pytest.fixture
def kb(tmp_path):
    """A KB with its own seed and data dir, so a test can never touch the
    checked-in corpus or the real gap log."""
    seed = tmp_path / "seed.csv"
    seed.write_text(
        "term,meaning,origin,region,first_seen,example,adult_friendly_explanation\n"
        "갓생,a disciplined productive life,net slang,ko,2020,갓생 살자,living well\n",
        encoding="utf-8",
    )
    return LocalSlangKB(seed_path=seed, data_dir=tmp_path)


@pytest.fixture
def store(tmp_path):
    return PendingStore(data_dir=tmp_path)


def _log(kb, *terms):
    for term in terms:
        kb.log_gap(term)


def _run(**kwargs):
    return asyncio.run(resolve_gaps(**kwargs))


# ── Acceptance: the job queues, it does not publish ──────────────────────────

def test_resolving_produces_pending_entries_not_live_ones(kb, store):
    _log(kb, "존잼", "존잼", "개꿀")

    stats = _run(kb=kb, store=store, resolver=MockSlangResolver())

    assert stats["resolved"] == 2
    assert {c.term for c in store.by_status(PENDING)} == {"존잼", "개꿀"}
    assert [t.term for t in kb.all_terms()] == ["갓생"], "nothing may go live unreviewed"
    assert kb.search("존잼", k=3) == [], "an unreviewed term must not be retrievable"


def test_promotion_puts_the_term_in_the_kb_and_it_becomes_retrievable(kb, store):
    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())

    promoted = promote("존잼", kb=kb, store=store)

    assert promoted is not None
    assert "존잼" in {t.term for t in kb.all_terms()}
    assert [r.term.term for r in kb.search("이거 존잼이다", k=3)] == ["존잼"]
    assert store.get("존잼").status == PROMOTED


def test_a_rejected_term_never_reaches_the_kb(kb, store):
    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())

    assert reject("존잼", "not actually slang", store=store) is True
    assert promote("존잼", kb=kb, store=store) is None
    assert "존잼" not in {t.term for t in kb.all_terms()}


# ── Acceptance: re-running is idempotent ────────────────────────────────────

def test_rerunning_queues_nothing_new(kb, store):
    _log(kb, "존잼", "개꿀")
    first = _run(kb=kb, store=store, resolver=MockSlangResolver())

    second = _run(kb=kb, store=store, resolver=MockSlangResolver())

    assert first["resolved"] == 2
    assert second["resolved"] == 0
    assert second["already_decided"] == 2
    assert len(store.all()) == 2, "a second run must not duplicate the queue"


def test_a_rejected_term_does_not_come_back_on_the_next_run(kb, store):
    """Otherwise every run re-resolves and re-queues everything a human has
    already said no to, and the queue becomes noise."""
    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())
    reject("존잼", store=store)

    _log(kb, "존잼", "존잼")  # hit again by real users
    stats = _run(kb=kb, store=store, resolver=MockSlangResolver())

    assert stats["resolved"] == 0
    assert store.get("존잼").status == REJECTED


def test_promoting_twice_writes_once(kb, store, tmp_path):
    """The KB was always correct here — `_load` keeps the last row for a term —
    but the backing CSV is append-only, so a second promotion used to add a row
    that only the loader's dedupe hid. Over a long-lived corpus that is a file
    that grows for no reason."""
    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())

    promote("존잼", kb=kb, store=store)
    rows_after_first = (tmp_path / "added_terms.csv").read_text(encoding="utf-8")
    promote("존잼", kb=kb, store=store)

    assert [t.term for t in kb.all_terms()].count("존잼") == 1
    assert (tmp_path / "added_terms.csv").read_text(encoding="utf-8") == rows_after_first


def test_promoting_restores_a_term_that_vanished_from_the_kb(kb, store):
    """Marked promoted but not actually present — a corpus restored from an old
    backup, say. The queue is the record of what was approved, so it should be
    able to put it back."""
    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())
    promote("존잼", kb=kb, store=store)

    kb._terms = [t for t in kb._terms if t.term != "존잼"]  # noqa: SLF001
    kb._vectors = kb._vectors[: len(kb._terms)]  # noqa: SLF001

    assert promote("존잼", kb=kb, store=store) is not None
    assert "존잼" in {t.term for t in kb.all_terms()}


def test_a_gap_the_kb_already_covers_is_skipped(kb, store):
    """The gap log is append-only and outlives the gap. It also holds terms a
    since-fixed matching bug reported as missing while they were in the KB all
    along — re-resolving those would spend money to relearn what we know."""
    _log(kb, "갓생", "갓생", "존잼")

    stats = _run(kb=kb, store=store, resolver=MockSlangResolver())

    assert stats["already_known"] == 1
    assert {c.term for c in store.all()} == {"존잼"}


# ── The human queue stays worth reading ─────────────────────────────────────

def test_a_resolver_verdict_of_not_slang_keeps_junk_out_of_the_queue(kb, store):
    """Junk filtering is the *resolver's* job, not a heuristic's.

    Deciding that "zzblargh nonsense" is not a word requires looking it up —
    which is exactly what the web-grounded resolver does and what no local rule
    can do. Running the real gap log through the mock queued both `zzblargh
    nonsense` (98 hits, from an old test leak) and `term0` for human review,
    and that is correct behaviour for a resolver that cannot search. So what is
    pinned here is the plumbing: an `is_slang=False` verdict never reaches a
    human. An earlier version of this test looked like it proved junk filtering
    and actually only exercised the length cap below.
    """

    class _Skeptical(MockSlangResolver):
        async def resolve(self, term, seen):
            if term.startswith("zzblargh"):
                return Candidate(term=term, is_slang=False, resolver="skeptical",
                                 seen=seen, note="no such word in any source")
            return await super().resolve(term, seen)

    _log(kb, "zzblargh nonsense")
    _log(kb, "존잼")

    stats = _run(kb=kb, store=store, resolver=_Skeptical())

    assert stats["resolved"] == 1
    assert stats["auto_rejected"] == 1
    assert [c.term for c in store.by_status(PENDING)] == ["존잼"]


def test_an_oversized_gap_never_reaches_the_resolver(kb, store):
    """The gap log records the phrase the model quoted, which is sometimes a
    whole clause. Paying for a web search on a sentence is waste."""
    _log(kb, "a very long quoted clause " * 5)

    calls: list[str] = []

    class _Counting(MockSlangResolver):
        async def resolve(self, term, seen):
            calls.append(term)
            return await super().resolve(term, seen)

    _run(kb=kb, store=store, resolver=_Counting())
    assert calls == []


def test_the_most_hit_gaps_are_resolved_first(kb, store):
    """With a budget of one call, it should be spent on what users actually hit."""
    _log(kb, "rare")
    _log(kb, "common", "common", "common")

    _run(kb=kb, store=store, resolver=MockSlangResolver(), max_terms=1)

    assert [c.term for c in store.all()] == ["common"]


def test_a_resolver_that_finds_nothing_does_not_queue_a_blank_entry(kb, store):
    class _Empty(SlangResolver):
        name = "empty"

        async def resolve(self, term, seen):
            return Candidate(term=term, is_slang=False, resolver=self.name,
                             seen=seen, note="no established meaning")

    _log(kb, "존잼")
    stats = _run(kb=kb, store=store, resolver=_Empty())

    assert stats["resolved"] == 0
    assert stats["auto_rejected"] == 1
    assert store.get("존잼").status == REJECTED


def test_one_failing_term_does_not_end_the_batch(kb, store):
    """This runs unattended. A single bad term must not cost the whole run."""

    class _Flaky(MockSlangResolver):
        async def resolve(self, term, seen):
            if term == "존잼":
                return Candidate(term=term, is_slang=False, resolver="flaky",
                                 seen=seen, note="resolver error: boom")
            return await super().resolve(term, seen)

    _log(kb, "존잼", "개꿀")
    stats = _run(kb=kb, store=store, resolver=_Flaky())

    assert stats["resolved"] == 1
    assert stats["auto_rejected"] == 1


def test_candidates_carry_the_sources_an_approver_would_check(kb, store):
    """Approval without evidence is a rubber stamp."""
    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())

    assert store.get("존잼").sources


# ── Storage behaves under real-world abuse ──────────────────────────────────

def test_a_truncated_queue_file_does_not_brick_curation(store, tmp_path):
    store.upsert(Candidate(term="존잼", meaning="fun"))
    path = tmp_path / "pending_terms.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + '{"term": "brok',
                    encoding="utf-8")

    assert [c.term for c in store.all()] == ["존잼"]


def test_the_queue_survives_an_unknown_field(store, tmp_path):
    """A file written by a later version must not crash an older reader."""
    path = tmp_path / "pending_terms.jsonl"
    path.write_text(
        json.dumps({"term": "존잼", "meaning": "fun", "invented_later": True}) + "\n",
        encoding="utf-8",
    )
    assert store.get("존잼").meaning == "fun"


def test_terms_are_matched_case_and_space_insensitively(store):
    store.upsert(Candidate(term="No  Cap", meaning="honestly"))
    assert store.get("no cap") is not None


def test_promoting_something_that_was_never_queued_is_a_no_op(kb, store):
    assert promote("never seen", kb=kb, store=store) is None
    assert [t.term for t in kb.all_terms()] == ["갓생"]


# ── Acceptance: this never runs during a request ────────────────────────────

def test_no_request_path_imports_the_curation_module():
    """A web-search call inside a caption or translation request would blow the
    <1s latency budget and bill per user. Keeping it out is structural, so it is
    asserted structurally rather than trusted."""
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    # An actual import, not the word "curation" in a comment — the first version
    # of this test flagged four files that merely discuss it.
    imports = re.compile(
        r"^\s*(?:from\s+[\w.]*\bcuration\b|import\s+[\w.]*\bcuration\b)", re.MULTILINE
    )
    offenders = [
        path.relative_to(backend)
        for folder in ("app", "services")
        for path in (backend / folder).rglob("*.py")
        if path.name != "curation.py" and imports.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"curation reached from a request path: {offenders}"


def test_the_resolver_defaults_to_the_free_mock(monkeypatch):
    """A batch job that silently spends money the first time someone runs it is
    a trap (INTRODUCTION §6)."""
    from services.genz.curation import get_slang_resolver

    monkeypatch.delenv("SLANG_RESOLVER_SERVICE", raising=False)
    assert isinstance(get_slang_resolver(), MockSlangResolver)


def test_the_real_resolver_asks_for_a_web_grounded_model(monkeypatch):
    """`:online` is the entire point — the plain model has the same blind spot
    that put the term in the gap log."""
    from services.genz.curation import OpenRouterSlangResolver

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o")
    assert OpenRouterSlangResolver().model == "openai/gpt-4o:online"

    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4o:online")
    assert OpenRouterSlangResolver().model == "openai/gpt-4o:online", "must not double-suffix"


def test_a_promoted_term_grounds_the_next_translation(kb, store, monkeypatch):
    """The loop only closes if a promoted term actually reaches the translation
    prompt — otherwise curation is bookkeeping."""
    import services.genz as genz_pkg
    from services.openrouter.real import _retrieve

    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())
    monkeypatch.setattr(genz_pkg, "get_slang_kb", lambda: kb)

    assert _retrieve("이거 존잼") == [], "not before a human approves it"
    promote("존잼", kb=kb, store=store)
    assert "존잼" in [t.term for t in _retrieve("이거 존잼")]


def test_a_promoted_term_is_a_well_formed_kb_entry(kb, store):
    """`add_term` writes straight to the corpus, so a malformed candidate would
    corrupt retrieval for every surface at once."""
    _log(kb, "존잼")
    _run(kb=kb, store=store, resolver=MockSlangResolver())
    promote("존잼", kb=kb, store=store)

    entry = next(t for t in kb.all_terms() if t.term == "존잼")
    assert isinstance(entry, SlangTerm)
    assert entry.meaning.strip()
    assert entry.context_text().strip()
