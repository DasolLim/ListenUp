"""Phase 5.2: RAG + LLM explanation — grounding, low-confidence fallback,
defensive JSON parsing, caching, and the /genz/explain route."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.genz.explainer import (
    MockGenZExplainer,
    OpenRouterGenZExplainer,
    _coerce,
)
from services.genz.kb import LocalSlangKB
from services.translate import cache as cache_module
from services.translate.cache import TranslationCache

client = TestClient(app)


@pytest.fixture
def fresh_cache(monkeypatch: pytest.MonkeyPatch) -> TranslationCache:
    isolated = TranslationCache()
    isolated._connected = True  # skip Redis probe → memory backend
    monkeypatch.setattr(cache_module, "_cache", isolated)
    return isolated


def test_known_term_is_grounded_high_confidence(tmp_path: Path) -> None:
    ex = MockGenZExplainer(kb=LocalSlangKB(data_dir=tmp_path))
    result = asyncio.run(ex.explain("that outfit is bussin, no cap"))
    assert result.confidence == "high"
    assert result.term == "bussin"
    assert "bussin" in result.grounded_terms


def test_unknown_term_is_low_confidence_and_logs_gap(tmp_path: Path) -> None:
    kb = LocalSlangKB(data_dir=tmp_path)
    ex = MockGenZExplainer(kb=kb)
    result = asyncio.run(ex.explain("qwerty zxcvb madeupword"))
    assert result.confidence == "low"
    assert result.grounded_terms == []
    gaps = kb.gaps()
    assert gaps and gaps[0]["query"] == "qwerty zxcvb madeupword"


def test_coerce_grounds_only_on_confident_match() -> None:
    kb = LocalSlangKB()
    strong = kb.search("bussin no cap")  # top score ~1.0
    data = {"term": "bussin", "plain_meaning": "really good"}
    grounded = _coerce(data, strong, "m", 10)
    assert grounded is not None and grounded.confidence == "high"
    # No matches → low confidence even with valid JSON.
    ungrounded = _coerce(data, [], "m", 10)
    assert ungrounded is not None and ungrounded.confidence == "low"


def test_coerce_rejects_unusable_json() -> None:
    assert _coerce({"origin": "x"}, [], "m", 0) is None  # no term/meaning


def test_real_explainer_parses_and_caches(
    monkeypatch: pytest.MonkeyPatch, fresh_cache: TranslationCache, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    ex = OpenRouterGenZExplainer(kb=LocalSlangKB(data_dir=tmp_path))
    calls = {"n": 0}

    async def fake_complete(text: str, context: str) -> tuple[str, int]:
        calls["n"] += 1
        # Fenced + prose-wrapped JSON exercises the defensive parser.
        return (
            "Sure! ```json\n"
            '{"term":"bussin","plain_meaning":"really good, usually food",'
            '"origin":"AAVE","first_seen":"2020","region":"US","example":"this is bussin",'
            '"adult_friendly_explanation":"It means delicious or excellent."}\n```',
            42,
        )

    monkeypatch.setattr(ex, "_complete", fake_complete)
    first = asyncio.run(ex.explain("bussin"))
    second = asyncio.run(ex.explain("bussin"))
    assert first.term == "bussin"
    assert first.confidence == "high"  # KB has bussin → grounded
    assert calls["n"] == 1  # second call served from cache
    assert second.cached is True


def test_explain_route_known_unknown_and_validation() -> None:
    known = client.post("/genz/explain", json={"text": "no cap that's bussin"})
    assert known.status_code == 200
    assert known.json()["confidence"] == "high"

    unknown = client.post("/genz/explain", json={"text": "zzblargh nonsense"})
    assert unknown.status_code == 200  # never crashes on unknown
    assert unknown.json()["confidence"] == "low"

    assert client.post("/genz/explain", json={"text": ""}).status_code == 422
