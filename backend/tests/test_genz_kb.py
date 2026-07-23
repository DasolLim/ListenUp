"""Phase 5.1: text embedder + slang KB retrieval, ingest, and gap logging."""

from pathlib import Path

from services.genz.base import EMBED_DIM
from services.genz.embedder import HashingTextEmbedder
from services.genz.kb import RELEVANCE_FLOOR, LocalSlangKB, SlangTerm


def test_embedder_deterministic_dim_and_discriminates() -> None:
    e = HashingTextEmbedder()
    a1 = e.embed("that outfit is bussin")
    a2 = e.embed("that outfit is bussin")
    b = e.embed("completely different sentence about taxes")
    assert len(a1) == EMBED_DIM
    assert a1 == a2  # deterministic across calls (stable for stored vectors)
    assert a1 != b


def test_kb_retrieves_known_slang() -> None:
    kb = LocalSlangKB()
    hits = kb.search("that outfit is bussin, no cap", k=3)
    assert hits, "expected KB matches"
    assert hits[0].term.term == "bussin"
    assert hits[0].score >= 0.9  # exact term present → lexical bonus lifts it high


def test_kb_korean_term() -> None:
    kb = LocalSlangKB()
    hits = kb.search("오늘부터 갓생 살 거야", k=1)
    assert hits and hits[0].term.term == "갓생"


def test_kb_unknown_returns_no_match() -> None:
    kb = LocalSlangKB()
    hits = kb.search("qwerty zxcvb nonsense nonword", k=3)
    assert all(h.score >= RELEVANCE_FLOOR for h in hits)
    assert not any(h.term.term for h in hits if h.score > 0.4)


def test_ingest_makes_term_retrievable(tmp_path: Path) -> None:
    kb = LocalSlangKB(data_dir=tmp_path)
    added = kb.add_term(
        SlangTerm(term="skibidi", meaning="absurdist meme nonsense", first_seen="2023")
    )
    assert added is True
    hits = kb.search("what does skibidi mean", k=1)
    assert hits and hits[0].term.term == "skibidi"
    # A reload picks up the persisted row too.
    assert any(t.term == "skibidi" for t in LocalSlangKB(data_dir=tmp_path).all_terms())


def test_gap_log_records_missing_terms(tmp_path: Path) -> None:
    kb = LocalSlangKB(data_dir=tmp_path)
    kb.log_gap("zzyzx-not-a-word")
    gaps = kb.gaps()
    assert gaps and gaps[0]["query"] == "zzyzx-not-a-word"
