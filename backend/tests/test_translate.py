import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.translate import cache as cache_module
from services.translate.cache import TranslationCache

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch: pytest.MonkeyPatch) -> TranslationCache:
    """Isolated in-memory cache per test (no Redis dependency in CI)."""
    isolated = TranslationCache()
    isolated._connected = True  # skip Redis probe → memory backend
    monkeypatch.setattr(cache_module, "_cache", isolated)
    return isolated


def test_mock_translates_to_target() -> None:
    response = client.post(
        "/translate", json={"text": "Hello, how are you?", "target_lang": "ko"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["translation"] == "[ko] Hello, how are you?"
    assert body["detectedSourceLang"] == "en"
    assert body["cached"] is False


def test_second_identical_request_hits_cache(fresh_cache: TranslationCache) -> None:
    payload = {"text": "Hello, how are you?", "target_lang": "ko"}
    first = client.post("/translate", json=payload).json()
    second = client.post("/translate", json=payload).json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["translation"] == first["translation"]
    assert second["characters"] == 0  # cache hits bill nothing
    assert fresh_cache.hits == 1 and fresh_cache.misses == 1


def test_unsupported_language_clear_error() -> None:
    response = client.post("/translate", json={"text": "hi", "target_lang": "xx"})
    assert response.status_code == 400
    assert "Unsupported target language 'xx'" in response.json()["detail"]


def test_source_language_detection_hints() -> None:
    response = client.post(
        "/translate", json={"text": "Hola, gracias por venir.", "target_lang": "en"}
    )
    assert response.json()["detectedSourceLang"] == "es"


def test_languages_endpoint_lists_supported() -> None:
    body = client.get("/translate/languages").json()
    assert body["ko"] == "Korean" and len(body) >= 20
