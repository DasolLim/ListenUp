"""Phase 5.5: KB maintenance (add/update) + gap-list logging via the API."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes.genz import kb_dep, require_user
from services.genz.kb import LocalSlangKB

client = TestClient(app)


@pytest.fixture
def kb(tmp_path: Path) -> Iterator[LocalSlangKB]:
    isolated = LocalSlangKB(data_dir=tmp_path)
    app.dependency_overrides[kb_dep] = lambda: isolated
    yield isolated
    app.dependency_overrides.clear()


def _auth() -> None:
    app.dependency_overrides[require_user] = lambda: "test-user"


def test_ingest_requires_auth(kb: LocalSlangKB) -> None:
    resp = client.post("/genz/terms", json={"term": "skibidi", "meaning": "meme nonsense"})
    assert resp.status_code == 401


def test_add_new_term_is_immediately_retrievable(kb: LocalSlangKB) -> None:
    _auth()
    # A term guaranteed not to exist in the curated seed.
    resp = client.post(
        "/genz/terms",
        json={"term": "florbglax", "meaning": "absurdist meme nonsense", "first_seen": "2099"},
    )
    assert resp.status_code == 201
    assert resp.json()["created"] is True
    # Retrievable via the API immediately…
    terms = client.get("/genz/terms").json()
    assert any(t["term"] == "florbglax" for t in terms)
    # …and via vector search on the same KB.
    hits = kb.search("what does florbglax mean")
    assert hits and hits[0].term.term == "florbglax"


def test_update_existing_term(kb: LocalSlangKB) -> None:
    _auth()
    resp = client.post(
        "/genz/terms",
        json={"term": "bussin", "meaning": "UPDATED: extremely good"},
    )
    assert resp.status_code == 201
    assert resp.json()["created"] is False  # updated, not created
    terms = client.get("/genz/terms").json()
    bussin = [t for t in terms if t["term"] == "bussin"]
    assert len(bussin) == 1  # no duplicate
    assert bussin[0]["meaning"] == "UPDATED: extremely good"


def test_gaps_requires_auth(kb: LocalSlangKB) -> None:
    assert client.get("/genz/gaps").status_code == 401


def test_gap_list_surfaces_missing_terms(kb: LocalSlangKB) -> None:
    _auth()
    kb.log_gap("zzyzx-unknown-term")
    gaps = client.get("/genz/gaps").json()
    assert gaps and gaps[0]["query"] == "zzyzx-unknown-term"
