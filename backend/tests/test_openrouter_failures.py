"""When the cultural pass can't run, the reason has to survive to the surface.

Reported from a real session: every line translated, no slang notes, no
register, and `502 Bad Gateway` repeating in the console. The 502 was correct —
the model provider was refusing the calls — but it said only "unavailable right
now", so there was no way to tell an expired key from an exhausted balance from
a model the account cannot reach. Those need three different fixes, and
`raise_for_status()` was discarding the provider's own explanation of which one
it was.

These pin that the explanation survives, and that a refusal which cannot recover
is not retried once per attempt for the length of a conversation.
"""

import asyncio
import json

import httpx
import pytest

from services.openrouter.base import CulturalUnavailable, ProviderError
from services.openrouter.real import OpenRouterTranslationService, _provider_detail


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


def _response(status: int, payload: dict | str) -> httpx.Response:
    if isinstance(payload, str):
        return httpx.Response(status, text=payload)
    return httpx.Response(status, json=payload)


# ── The provider's words survive ─────────────────────────────────────────────


def test_the_provider_error_message_is_extracted():
    response = _response(402, {"error": {"message": "Insufficient credits", "code": 402}})
    assert _provider_detail(response) == "Insufficient credits"


def test_a_bare_message_field_is_also_read():
    assert _provider_detail(_response(400, {"message": "model not found"})) == "model not found"


def test_a_non_json_body_falls_back_to_the_text():
    assert "gateway" in _provider_detail(_response(502, "upstream gateway error")).lower()


def test_an_empty_body_still_names_the_status():
    assert _provider_detail(_response(418, "")) == "HTTP 418"


def test_the_message_is_truncated_so_it_can_be_shown():
    response = _response(400, {"error": {"message": "x" * 500}})
    assert len(_provider_detail(response)) == 200


def test_newlines_cannot_break_the_log_line():
    response = _response(400, {"error": {"message": "bad\nrequest"}})
    assert "\n" not in _provider_detail(response)


# ── Retry policy ─────────────────────────────────────────────────────────────


class _CountingService(OpenRouterTranslationService):
    """Real retry logic; scripted HTTP outcome."""

    def __init__(self, status: int, payload) -> None:
        super().__init__()
        self.calls = 0
        self._status = status
        self._payload = payload

    async def _complete(self, text, target_lang, strict_nudge, grounding=()):
        self.calls += 1
        response = _response(self._status, self._payload)
        raise ProviderError(
            self._status,
            _provider_detail(response),
            retryable=self._status in (408, 409, 429) or self._status >= 500,
        )


def _run(service, text="that movie was fire"):
    return asyncio.run(service.translate(text, "ko"))


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404])
def test_an_unrecoverable_refusal_is_not_retried(status, monkeypatch):
    """A key, a balance or a model name will not fix itself between two attempts
    a few milliseconds apart, and live captions send one of these per sentence."""
    monkeypatch.setattr("services.openrouter.real._retrieve", lambda *a, **k: [])
    service = _CountingService(status, {"error": {"message": "nope"}})
    with pytest.raises(CulturalUnavailable):
        _run(service)
    assert service.calls == 1, f"{status} should not be retried"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_a_transient_refusal_is_retried_once(status, monkeypatch):
    monkeypatch.setattr("services.openrouter.real._retrieve", lambda *a, **k: [])
    service = _CountingService(status, {"error": {"message": "busy"}})
    with pytest.raises(CulturalUnavailable):
        _run(service)
    assert service.calls == 2, f"{status} should get the one retry"


# ── The reason reaches the caller ────────────────────────────────────────────


def test_the_reason_is_raised_rather_than_swallowed(monkeypatch):
    monkeypatch.setattr("services.openrouter.real._retrieve", lambda *a, **k: [])
    service = _CountingService(402, {"error": {"message": "Insufficient credits"}})
    with pytest.raises(CulturalUnavailable) as caught:
        _run(service)
    assert "Insufficient credits" in caught.value.reason


def test_unparseable_json_reports_that_specifically(monkeypatch):
    """A different fix from a provider refusal: the model answered, the answer
    was unusable."""
    monkeypatch.setattr("services.openrouter.real._retrieve", lambda *a, **k: [])

    class _Garbage(OpenRouterTranslationService):
        calls = 0

        async def _complete(self, text, target_lang, strict_nudge, grounding=()):
            type(self).calls += 1
            return "I'm afraid I can't do that", 10

    service = _Garbage()
    with pytest.raises(CulturalUnavailable) as caught:
        _run(service)
    assert "JSON" in caught.value.reason
    assert _Garbage.calls == 2, "bad JSON is what the strictness nudge exists for"


def test_a_transport_failure_names_itself(monkeypatch):
    monkeypatch.setattr("services.openrouter.real._retrieve", lambda *a, **k: [])

    class _Offline(OpenRouterTranslationService):
        async def _complete(self, text, target_lang, strict_nudge, grounding=()):
            raise httpx.ConnectError("no route to host")

    with pytest.raises(CulturalUnavailable) as caught:
        _run(_Offline())
    assert "provider" in caught.value.reason.lower()


# ── Through the route ────────────────────────────────────────────────────────


def test_the_endpoint_returns_the_reason_in_its_502(monkeypatch):
    """The whole point: the notice on screen can name the cause."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.plans import PLANS
    from app.routes.billing import Caller
    from app.usage import EMPTY, Usage
    from tests.conftest import TEST_USER

    class _Refusing:
        async def translate(self, text, target_lang):
            raise CulturalUnavailable("Insufficient credits")

    monkeypatch.setattr(
        "app.routes.translate.get_enhanced_translation_service", lambda: _Refusing()
    )

    who = Caller(
        TEST_USER,
        "t",
        {"status": "active", "tier": "pro"},
        PLANS["pro"],
        Usage(dict(EMPTY), period_start="2026-08-01", period_end="2026-09-01"),
    )

    async def _record(metric, amount):
        return None

    who.record = _record  # type: ignore[method-assign]
    app.dependency_overrides[__import__("app.routes.billing", fromlist=["caller"]).caller] = (
        lambda: who
    )
    try:
        client = TestClient(app)
        response = client.post(
            "/translate/enhanced",
            json={"text": "that movie was fire", "target_lang": "ko"},
            headers={"Authorization": "Bearer t"},
        )
        assert response.status_code == 502
        assert "Insufficient credits" in json.dumps(response.json())
    finally:
        app.dependency_overrides.clear()
