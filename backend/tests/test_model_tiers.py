"""The cultural pass is optional and its model is chosen by tier.

Two things are being protected. First the wallet: the cultural pass is metered,
so a user who does not want slang explanations must be able to stop paying for
them, and a user who picks the dearer model must draw down their allowance at
the rate it actually costs rather than being subsidised.

Second the boundary: the client sends a **tier**, never a model id. A request
that could name its own model could name a $75/M one, and the bill would land
on us. That is a security property, not a preference, so it is pinned here.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.plans import ENHANCED_COST_RATIO, PLANS
from app.routes.billing import Caller, caller
from app.usage import EMPTY, Usage
from services.openrouter.tiers import DEFAULT_TIER, TIERS, catalogue, resolve
from tests.conftest import TEST_USER

client = TestClient(app)


# ── The tier table itself ────────────────────────────────────────────────────


def test_every_tier_is_complete_enough_to_render():
    for tier in TIERS:
        assert tier.key and tier.model and tier.label and tier.blurb
        assert tier.usd_per_1k > 0, f"{tier.key} has no measured cost"
        assert tier.p50_ms > 0, f"{tier.key} has no measured latency"
        assert tier.cost_weight > 0


def test_tiers_are_ordered_cheapest_first():
    """The picker reads top to bottom, so the order is part of the meaning."""
    costs = [tier.usd_per_1k for tier in TIERS]
    assert costs == sorted(costs)


def test_the_default_tier_exists_and_is_the_cheapest():
    default = resolve(DEFAULT_TIER)
    assert default.key == DEFAULT_TIER
    assert default.usd_per_1k == min(t.usd_per_1k for t in TIERS)


def test_cost_weight_tracks_the_measured_cost_ratio():
    """Otherwise the cheap tier subsidises the dear one and the advertised
    allowance stops meaning a fixed amount of anything."""
    base = resolve(DEFAULT_TIER)
    for tier in TIERS:
        ratio = tier.usd_per_1k / base.usd_per_1k
        assert abs(tier.cost_weight - ratio) < 1.0, (
            f"{tier.key} costs {ratio:.1f}x the default but is weighted "
            f"{tier.cost_weight}x"
        )


@pytest.mark.parametrize(
    "supplied", ["", None, "  ", "nonsense", "gpt-4o", "openai/gpt-5.4", "BALANCED"]
)
def test_an_unusable_tier_key_falls_back_rather_than_failing(supplied):
    """A stale client sending a retired tier name is a cosmetic mismatch, and
    must not become a broken feature. Note a raw *model id* is not a tier and
    gets the default — the client cannot smuggle a model through this field."""
    assert resolve(supplied) in TIERS


def test_a_client_cannot_name_its_own_model():
    """The boundary that keeps an expensive model off our bill."""
    expensive = resolve("anthropic/claude-opus-4.1")
    assert expensive.model in {t.model for t in TIERS}


def test_the_catalogue_marks_exactly_one_default():
    entries = catalogue()
    assert sum(1 for e in entries if e["default"]) == 1
    assert {e["key"] for e in entries} == {t.key for t in TIERS}


# ── Through the API ──────────────────────────────────────────────────────────


def test_the_models_endpoint_is_public():
    """The picker needs it before anything is translated."""
    response = client.get("/translate/models")
    assert response.status_code == 200
    assert response.json()["tiers"] == catalogue()


@pytest.fixture
def as_pro():
    """A Pro caller whose metered amounts are captured."""
    recorded: list[tuple[str, int]] = []

    who = Caller(
        TEST_USER,
        "t",
        {"status": "active", "tier": "pro"},
        PLANS["pro"],
        Usage(dict(EMPTY), period_start="2026-08-01", period_end="2026-09-01"),
    )

    async def _record(metric, amount):
        recorded.append((metric, amount))

    who.record = _record  # type: ignore[method-assign]
    app.dependency_overrides[caller] = lambda: who
    yield recorded
    app.dependency_overrides.clear()


TEXT = "that movie was straight fire, no cap"


def _enhanced(**extra):
    return client.post(
        "/translate/enhanced",
        json={"text": TEXT, "target_lang": "ko", **extra},
        headers={"Authorization": "Bearer t"},
    )


def test_the_tier_reaches_the_service_and_comes_back(as_pro):
    response = _enhanced(tier="thorough")
    assert response.status_code == 200
    assert response.json()["tier"] == "thorough"


def test_no_tier_means_the_default(as_pro):
    assert _enhanced().json()["tier"] == DEFAULT_TIER


def test_the_dearer_tier_spends_more_allowance(as_pro):
    """The whole reason `cost_weight` exists."""
    _enhanced(tier="balanced")
    _enhanced(tier="thorough")
    balanced, thorough = (amount for _, amount in as_pro)

    base = resolve("balanced")
    dear = resolve("thorough")
    assert thorough > balanced
    assert thorough / balanced == pytest.approx(dear.cost_weight / base.cost_weight, rel=0.15)


def test_the_baseline_tier_still_meters_the_documented_ratio(as_pro):
    """Weighting must not have quietly changed what the standard pass costs."""
    _enhanced(tier="balanced")
    _, amount = as_pro[0]
    assert amount == max(1, round(len(TEXT) * ENHANCED_COST_RATIO * 1.0))


def test_switching_tier_reaches_the_service_as_a_different_tier(as_pro):
    first = _enhanced(tier="balanced").json()
    second = _enhanced(tier="thorough").json()
    assert first["tier"] != second["tier"]


def test_the_real_cache_key_follows_the_model(monkeypatch):
    """The model is part of the *real* service's cache key. Without that the
    picker looks broken in both directions: switch up and nothing improves,
    switch down and nothing gets cheaper.

    Exercised against `OpenRouterTranslationService` rather than through the
    API, because the API runs the mock — whose key is its own, so it would pass
    this whether the real key were right or wrong. An earlier version of this
    test did exactly that and survived the key being mutated.
    """
    import asyncio

    from services.openrouter.real import OpenRouterTranslationService
    from services.translate import cache as cache_module

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("services.openrouter.real._retrieve", lambda *a, **k: [])
    isolated = cache_module.TranslationCache()
    isolated._connected = True  # memory only; never reaches Redis
    monkeypatch.setattr(cache_module, "_cache", isolated)

    seen: list[str] = []

    async def _complete(
        _self, text, target_lang, nudge, grounding=(), model=None, reasoning_effort=None
    ):  # noqa: ARG001
        seen.append(model)
        return json.dumps({"translation": "x", "register": "casual", "slang_notes": []}), 5

    monkeypatch.setattr(OpenRouterTranslationService, "_complete", _complete)
    service = OpenRouterTranslationService()

    asyncio.run(service.translate(TEXT, "ko", resolve("balanced")))
    asyncio.run(service.translate(TEXT, "ko", resolve("thorough")))
    # Same sentence, two tiers: the second must not be served the first's answer.
    assert seen == [resolve("balanced").model, resolve("thorough").model]

    # And the same tier twice *is* a cache hit, or the key is simply broken.
    asyncio.run(service.translate(TEXT, "ko", resolve("balanced")))
    assert len(seen) == 2, "identical request should have been cached"


def test_the_reasoning_effort_of_the_tier_is_sent(monkeypatch):
    """The cheap tier is only cheap because thinking is capped; if the effort
    stops being sent it silently costs 4x and runs 3x slower."""
    import asyncio

    from services.openrouter.real import OpenRouterTranslationService
    from services.translate import cache as cache_module

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("services.openrouter.real._retrieve", lambda *a, **k: [])
    isolated = cache_module.TranslationCache()
    isolated._connected = True
    monkeypatch.setattr(cache_module, "_cache", isolated)

    seen: list[str | None] = []

    async def _complete(
        _self, text, target_lang, nudge, grounding=(), model=None, reasoning_effort=None
    ):  # noqa: ARG001
        seen.append(reasoning_effort)
        return json.dumps({"translation": "x", "register": "casual", "slang_notes": []}), 5

    monkeypatch.setattr(OpenRouterTranslationService, "_complete", _complete)
    service = OpenRouterTranslationService()
    asyncio.run(service.translate(TEXT, "ko", resolve("balanced")))
    assert seen == [resolve("balanced").reasoning_effort]


def test_the_request_body_carries_the_effort_only_when_set():
    """`None` must mean "leave the model's default alone", not "effort: none"."""
    from services.openrouter.real import OpenRouterTranslationService as S

    capped = S._body("hi", "sys", "some/model", "low")
    assert capped["reasoning"] == {"effort": "low"}
    assert "reasoning" not in S._body("hi", "sys", "some/model", None)


def test_declining_the_cultural_pass_costs_nothing(as_pro):
    """The client's half of the switch: when explanations are off the request is
    never sent, so nothing is metered. Asserted as the absence of a call, since
    that is exactly what the frontend guarantees."""
    assert as_pro == []


def test_a_refused_tier_never_reaches_the_provider_as_a_model_name(as_pro):
    """Belt and braces on the boundary: whatever the client sends, the model the
    service is asked for is one of ours."""
    response = _enhanced(tier="../../etc/passwd")
    assert response.status_code == 200
    assert response.json()["tier"] == DEFAULT_TIER
    assert json.loads(response.text)["model"] in {t.model for t in TIERS} | {"mock"}


def test_the_service_fallback_model_matches_the_default_tier():
    """One source of truth. The constant read `openai/gpt-4o` for a while after
    the default tier had moved to gemini, and was reported as the live model on
    the strength of reading it — the route always passes a tier, so it never
    was. A constant that can disagree with reality is worse than no constant."""
    from services.openrouter.real import DEFAULT_MODEL

    assert DEFAULT_MODEL == resolve(DEFAULT_TIER).model
