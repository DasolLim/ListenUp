import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.openrouter.base import coerce_enhanced, parse_llm_json
from services.translate import cache as cache_module
from services.translate.cache import TranslationCache

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch: pytest.MonkeyPatch) -> TranslationCache:
    isolated = TranslationCache()
    isolated._connected = True
    monkeypatch.setattr(cache_module, "_cache", isolated)
    return isolated


# ── defensive JSON parsing (the spec's error-check focus) ──────────


def test_parse_plain_json() -> None:
    assert parse_llm_json('{"translation": "hola"}') == {"translation": "hola"}


def test_parse_fenced_json() -> None:
    raw = '```json\n{"translation": "hola", "register": "casual"}\n```'
    assert parse_llm_json(raw)["translation"] == "hola"


def test_parse_json_wrapped_in_prose() -> None:
    raw = 'Sure! Here is your JSON:\n{"translation": "hola", "slang_notes": []}\nHope that helps!'
    assert parse_llm_json(raw)["translation"] == "hola"


def test_parse_json_with_braces_inside_strings() -> None:
    raw = '{"translation": "use {curly} braces", "register": "casual"}'
    assert parse_llm_json(raw)["translation"] == "use {curly} braces"


def test_parse_garbage_returns_none() -> None:
    assert parse_llm_json("I cannot help with that.") is None
    assert parse_llm_json('{"translation": "unterminated') is None
    assert parse_llm_json("[1, 2, 3]") is None


def test_coerce_rejects_missing_translation() -> None:
    assert coerce_enhanced({"register": "casual"}, "m", 0) is None


def test_coerce_drops_malformed_notes_keeps_good() -> None:
    result = coerce_enhanced(
        {
            "translation": "hola",
            "slang_notes": [
                {"phrase": "no cap", "meaning": "no lie"},
                {"phrase": "missing meaning"},
                "not even a dict",
            ],
        },
        "m",
        0,
    )
    assert result is not None
    assert len(result.slang_notes) == 1


# ── endpoint behavior (mock service) ───────────────────────────────


def test_enhanced_endpoint_returns_notes_for_slang() -> None:
    response = client.post(
        "/translate/enhanced",
        json={"text": "That movie was the GOAT, no cap.", "target_lang": "ko"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["translation"].startswith("[ko+]")
    assert body["register"] == "slang-heavy"
    phrases = {n["phrase"] for n in body["slangNotes"]}
    assert {"no cap", "GOAT"} <= phrases


def test_enhanced_endpoint_cache_hit_on_repeat() -> None:
    payload = {"text": "That movie was the GOAT, no cap.", "target_lang": "ko"}
    first = client.post("/translate/enhanced", json=payload).json()
    second = client.post("/translate/enhanced", json=payload).json()
    assert first["cached"] is False and second["cached"] is True
    assert second["slangNotes"] == first["slangNotes"]


def test_model_swappable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.openrouter.factory import get_enhanced_translation_service
    from services.openrouter.real import OpenRouterTranslationService

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
    assert OpenRouterTranslationService().model == "anthropic/claude-haiku-4.5"
    get_enhanced_translation_service.cache_clear()
