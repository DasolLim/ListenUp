import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.translate import cache as cache_module
from services.translate.cache import TranslationCache

client = TestClient(app)



# These tests exercise translation/explanation behaviour, not billing, so the
# paywall is lifted for the module. Kept as an explicit override rather than a
# global one in conftest so tests/test_billing.py still meets the real guard.
@pytest.fixture(autouse=True)
def _entitled():
    # Pro, with nothing spent: these suites test translation and explanation
    # behaviour, not allowances. The allowance paths have their own tests in
    # test_plans_and_usage.py.
    from tests.conftest import acting_as

    with acting_as("pro"):
        yield


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
        "/translate", json={"text": "안녕하세요, 감사합니다.", "target_lang": "en"}
    )
    assert response.json()["detectedSourceLang"] == "ko"


def test_languages_endpoint_is_english_and_korean_only() -> None:
    body = client.get("/translate/languages").json()
    assert body == {"en": "English", "ko": "Korean"}
