"""Tiers, allowances, and metering.

The tests are written against the behaviour a *user* would notice — a refusal
that names the wrong plan, a cached phrase that silently costs an hour, a Pro
subscriber dropped to Free because an env var is missing — rather than against
the shape of the code. Several of them exist because the obvious implementation
gets them wrong.
"""

import json
import time

import pytest
import stripe
from fastapi.testclient import TestClient

from app.main import app
from app.plans import CHARS_PER_HOUR, ENHANCED_COST_RATIO, PLANS, plan_for
from app.routes.billing import plan_for_row, tier_for_price
from app.usage import EMPTY, Usage, allowance
from tests.conftest import acting_as

client = TestClient(app)


# ── The tier table itself ────────────────────────────────────────────────────
#
# Pinned to the numbers that were sold. If a limit changes these fail, which is
# correct: changing an advertised allowance is a product decision and should
# never be a silent diff.

def test_the_three_tiers_match_what_is_advertised():
    free, basic, pro = PLANS["free"], PLANS["basic"], PLANS["pro"]

    assert (free.price_usd, basic.price_usd, pro.price_usd) == (0.0, 7.99, 14.99)

    assert free.limit("captions") == 3 * 3600
    assert basic.limit("captions") == 12 * 3600
    assert pro.limit("captions") == 36 * 3600

    assert free.limit("translated") == 0  # not included at all
    assert basic.limit("translated") == 3 * CHARS_PER_HOUR
    assert pro.limit("translated") == 6 * CHARS_PER_HOUR

    assert (free.limit("explain"), basic.limit("explain")) == (5, 100)
    assert pro.limit("explain") is None  # unlimited

    assert (free.profiles, basic.profiles, pro.profiles) == (1, 4, 4)
    assert (free.voice_cloning, basic.voice_cloning, pro.voice_cloning) == (False, False, True)

    assert (free.limit("cloud_tts"), basic.limit("cloud_tts")) == (0, 0)
    assert pro.limit("cloud_tts") == 30 * 60


def test_captions_are_included_on_every_tier():
    """The accessibility core. Metered everywhere, walled nowhere."""
    for plan in PLANS.values():
        assert plan.includes("captions")
        assert plan.limit("captions") > 0


# ── Allowance arithmetic ─────────────────────────────────────────────────────

def _usage(**used: int) -> Usage:
    totals = dict(EMPTY)
    totals.update(used)
    return Usage(totals, period_end="2026-09-12T00:00:00+00:00")


def test_a_metric_the_plan_excludes_is_blocked_but_not_exhausted():
    """These are different states and must stay distinguishable: one says
    'upgrade', the other says 'wait until the 12th'. Collapsing them is how a
    Free user gets told they've used up something they never had."""
    spent = allowance(PLANS["free"], _usage(), "translated")
    assert spent.blocked is True
    assert spent.included is False
    assert spent.exhausted is False  # nothing was consumed
    assert spent.remaining == 0


def test_unlimited_never_blocks_or_warns():
    spent = allowance(PLANS["pro"], _usage(explain=10_000_000), "explain")
    assert spent.unlimited is True
    assert (spent.blocked, spent.warning, spent.exhausted) == (False, False, False)
    assert spent.remaining is None


def test_the_warning_fires_at_eighty_percent_and_stops_at_the_limit():
    limit = PLANS["basic"].limit("explain")
    assert allowance(PLANS["basic"], _usage(explain=int(limit * 0.79)), "explain").warning is False
    assert allowance(PLANS["basic"], _usage(explain=int(limit * 0.80)), "explain").warning is True
    assert allowance(PLANS["basic"], _usage(explain=int(limit * 0.99)), "explain").warning is True
    # At the limit it is exhausted, not "warning" — the UI shows a different
    # state, and a bar that is amber at 100% reads as "nearly there".
    at_limit = allowance(PLANS["basic"], _usage(explain=limit), "explain")
    assert (at_limit.warning, at_limit.exhausted, at_limit.blocked) == (False, True, True)


def test_ratio_is_clamped_so_a_bar_cannot_overflow():
    spent = allowance(PLANS["basic"], _usage(explain=10_000), "explain")
    assert spent.ratio == 1.0
    assert spent.remaining == 0


# ── Refusals say the three things the rule requires ──────────────────────────

def test_free_is_refused_translation_and_told_which_plan_has_it():
    with acting_as("free"):
        response = client.post("/translate", json={"text": "hello", "target_lang": "ko"})
    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["reason"] == "not_included"
    assert detail["upgradeTo"] == "basic"


def test_at_the_limit_the_refusal_names_the_reset_date():
    """'When does this come back' is the most common support question; the API
    must answer it without the client having to work it out."""
    with acting_as("basic", translated=3 * CHARS_PER_HOUR):
        response = client.post("/translate", json={"text": "hello", "target_lang": "ko"})
    assert response.status_code == 402
    detail = response.json()["detail"]
    assert detail["reason"] == "limit_reached"
    assert detail["resetsAt"] == "2026-09-12T00:00:00+00:00"
    assert detail["upgradeTo"] == "pro"
    assert detail["limit"] == 3 * CHARS_PER_HOUR


def test_pro_at_its_limit_is_not_told_to_upgrade_to_pro():
    with acting_as("pro", translated=6 * CHARS_PER_HOUR):
        response = client.post("/translate", json={"text": "hello", "target_lang": "ko"})
    assert response.json()["detail"]["upgradeTo"] is None


def test_just_under_the_limit_still_works():
    """Proves the refusals above fire for the right reason. A gate that blocked
    everything would pass every test that only checks for 402."""
    with acting_as("basic", translated=3 * CHARS_PER_HOUR - 1):
        assert client.post(
            "/translate", json={"text": "hello", "target_lang": "ko"}
        ).status_code == 200


# ── Explain: per-tier lookups ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "tier,used,expected",
    [
        ("free", 4, 200),
        ("free", 5, 402),
        ("basic", 99, 200),
        ("basic", 100, 402),
        ("pro", 1_000_000, 200),  # unlimited
    ],
)
def test_explain_lookups_follow_the_tier(tier, used, expected):
    with acting_as(tier, explain=used):
        response = client.post("/genz/explain", json={"text": "no cap"})
    assert response.status_code == expected


# ── Metering tracks cost, not requests ───────────────────────────────────────

def test_a_cached_translation_spends_nothing(monkeypatch):
    """`characters` is 0 on a cache hit, so a repeated phrase must not draw down
    the allowance. Users repeat themselves constantly in conversation; charging
    for it would make the advertised hours a lie."""
    recorded: list[tuple[str, int]] = []

    async def _record(_token, metric, amount):
        recorded.append((metric, amount))

    monkeypatch.setattr("app.usage.record", _record)

    with acting_as("pro"):
        first = client.post("/translate", json={"text": "the same line", "target_lang": "ko"})
        second = client.post("/translate", json={"text": "the same line", "target_lang": "ko"})

    assert (first.status_code, second.status_code) == (200, 200)
    assert second.json()["cached"] is True
    # Exactly one billable record, from the first (uncached) call.
    assert [amount for metric, amount in recorded if metric == "translated" and amount > 0] == [
        len("the same line")
    ]


def test_the_enhanced_pass_is_metered_at_its_share_of_cost(monkeypatch):
    """Live captions send every line through both lanes. Metering each at full
    character weight would charge twice for one sentence and quietly halve the
    advertised allowance."""
    recorded: list[tuple[str, int]] = []

    async def _record(_token, metric, amount):
        recorded.append((metric, amount))

    monkeypatch.setattr("app.usage.record", _record)

    text = "x" * 100
    with acting_as("pro"):
        client.post("/translate/enhanced", json={"text": text, "target_lang": "ko"})

    assert recorded == [("translated", round(100 * ENHANCED_COST_RATIO))]
    assert recorded[0][1] < 100  # strictly cheaper than the fast lane


def test_a_same_language_request_is_free():
    """The short-circuit returns the text untouched without calling a provider,
    so it must not spend allowance either."""
    with acting_as("basic", translated=3 * CHARS_PER_HOUR - 1):
        response = client.post(
            "/translate", json={"text": "hello", "target_lang": "en", "source_lang": "en"}
        )
    assert response.status_code == 200
    assert response.json()["characters"] == 0


# ── Plan resolution ──────────────────────────────────────────────────────────

def test_a_lapsed_subscription_resolves_to_free():
    row = {"status": "canceled", "tier": "pro", "current_period_end": "2020-01-01T00:00:00+00:00"}
    assert plan_for_row(row).tier == "free"


def test_a_cancelled_subscription_keeps_its_tier_until_the_period_ends():
    """They paid for the month. Revoking on the cancel click would be taking
    money for time not served."""
    row = {"status": "canceled", "tier": "pro", "current_period_end": "2099-01-01T00:00:00+00:00"}
    assert plan_for_row(row).tier == "pro"


def test_an_entitled_row_with_an_unknown_tier_falls_back_to_basic_not_free():
    """The likely cause is our own misconfigured env, not anything the customer
    did. Dropping a paying subscriber to Free would be the worse failure."""
    row = {"status": "active", "tier": "enterprise-typo", "user_id": "u"}
    assert plan_for_row(row).tier == "basic"


def test_an_unpaid_row_never_grants_a_paid_plan():
    for status in ("incomplete", "past_due", "unpaid", "none", "incomplete_expired"):
        assert plan_for_row({"status": status, "tier": "pro"}).tier == "free"


def test_plan_for_degrades_rather_than_raising():
    for value in (None, "", "PRO", "nonsense", "free"):
        assert plan_for(value).tier in {"free", "pro"}
    assert plan_for("PRO").tier == "pro"  # case-insensitive


# ── Stripe: price → tier ─────────────────────────────────────────────────────

def test_price_ids_map_to_tiers(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_BASIC", "price_basic_123")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_456")
    assert tier_for_price("price_basic_123") == "basic"
    assert tier_for_price("price_pro_456") == "pro"
    assert tier_for_price("price_unknown") is None
    assert tier_for_price(None) is None


def test_the_webhook_reads_the_tier_from_the_price_not_the_metadata(monkeypatch):
    """Metadata records what we asked for; the price is what Stripe will bill.
    If a user switches plan in the portal, only the price changes."""
    monkeypatch.setenv("STRIPE_PRICE_BASIC", "price_basic_123")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_456")
    from app.routes.billing import _tier_of

    subscription = {
        "id": "sub_1",
        "metadata": {"tier": "basic"},  # stale: they upgraded in the portal
        "items": {"data": [{"price": {"id": "price_pro_456"}}]},
    }
    assert _tier_of(subscription) == "pro"


def test_the_webhook_falls_back_to_metadata_when_the_price_is_unrecognised(monkeypatch):
    monkeypatch.delenv("STRIPE_PRICE_BASIC", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_PRO", raising=False)
    from app.routes.billing import _tier_of

    assert _tier_of({"id": "sub_1", "metadata": {"tier": "pro"}, "items": {"data": []}}) == "pro"


def test_the_webhook_never_raises_on_a_shapeless_subscription():
    """An exception here is a 5xx, and Stripe retries 5xx for days."""
    from app.routes.billing import _tier_of

    for subscription in ({}, {"items": None}, {"items": {"data": None}}, {"items": {"data": [{}]}}):
        assert _tier_of(subscription) in {"basic", "pro"}


def test_a_tier_change_webhook_is_written_through(monkeypatch):
    """Upgrading in the portal must land in our table, or the user pays Pro
    prices and gets Basic allowances."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_tier")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_456")
    written: list[dict] = []

    async def _service_rest(_method, _path, *, json=None, **_kwargs):
        written.append(json)

        class _R:
            status_code = 201

        return _R()

    monkeypatch.setattr("app.supa.service_rest", _service_rest)

    payload = {
        "id": "evt_tier",
        "object": "event",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "type": "customer.subscription.updated",
        "livemode": False,
        "pending_webhooks": 0,
        "request": {"id": None, "idempotency_key": None},
        "data": {"object": {
            "id": "sub_9",
            "object": "subscription",
            "customer": "cus_9",
            "status": "active",
            "metadata": {"user_id": "11111111-1111-1111-1111-111111111111"},
            "items": {"data": [{"price": {"id": "price_pro_456"}}]},
        }},
    }
    body = json.dumps(payload)
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(f"{ts}.{body}", "whsec_tier")
    response = client.post(
        "/billing/webhook", content=body, headers={"stripe-signature": f"t={ts},v1={sig}"}
    )
    assert response.status_code == 200
    assert written and written[0]["tier"] == "pro"


# ── Checkout: plan choice and the Pro launch discount ────────────────────────

def test_checkout_rejects_an_unknown_plan():
    with acting_as("free"):
        response = client.post("/billing/checkout", json={"plan": "platinum"})
    assert response.status_code in (400, 503)
    if response.status_code == 400:
        assert "basic or pro" in response.json()["detail"].lower()


def test_checkout_refuses_a_second_subscription():
    with acting_as("pro"):
        response = client.post("/billing/checkout", json={"plan": "pro"})
    assert response.status_code == 400
    assert "already" in response.json()["detail"].lower()


def test_the_discount_is_only_advertised_when_a_coupon_exists(monkeypatch):
    """Promising 20% off and then not applying it at checkout is worse than
    never mentioning it."""
    monkeypatch.delenv("STRIPE_COUPON_PRO_FIRST_MONTH", raising=False)
    assert client.get("/billing/plans").json()["proFirstMonthDiscount"] == 0

    monkeypatch.setenv("STRIPE_COUPON_PRO_FIRST_MONTH", "promo_pro20")
    assert client.get("/billing/plans").json()["proFirstMonthDiscount"] == 20


def test_the_plans_endpoint_is_public():
    """The pricing page renders before sign-in."""
    response = client.get("/billing/plans")
    assert response.status_code == 200
    assert [p["tier"] for p in response.json()["plans"]] == ["free", "basic", "pro"]


def test_the_discount_is_applied_to_pro_and_not_to_basic(monkeypatch):
    """The coupon is a Pro launch incentive. Attaching it to Basic would be a
    silent 20% margin loss on the tier with the thinner margin."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.setenv("STRIPE_PRICE_BASIC", "price_basic_123")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_456")
    monkeypatch.setenv("STRIPE_COUPON_PRO_FIRST_MONTH", "promo_pro20")
    captured: list[dict] = []

    class _Session:
        url = "https://checkout.stripe.test/session"

    def _create(**kwargs):
        captured.append(kwargs)
        return _Session()

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(_create))
    monkeypatch.setattr(
        stripe.Customer, "create", staticmethod(lambda **_k: type("C", (), {"id": "cus_x"})())
    )

    with acting_as("free"):
        client.post("/billing/checkout", json={"plan": "basic"})
        client.post("/billing/checkout", json={"plan": "pro"})

    basic_args, pro_args = captured
    assert "discounts" not in basic_args
    assert pro_args["discounts"] == [{"coupon": "promo_pro20"}]
    # The trial rides on both, and the chosen tier travels with the subscription
    # so the webhook can attribute it even before the first invoice.
    for args in (basic_args, pro_args):
        assert args["subscription_data"]["trial_period_days"] == 7
    assert pro_args["subscription_data"]["metadata"]["tier"] == "pro"


# ── The guard cannot be demoted to a request parameter ───────────────────────
#
# The original paywall bug: `Depends` was not imported, FastAPI silently turned
# the dependency into a query parameter, and every paid endpoint became free.
# The same failure is possible with the new `requires(...)` dependencies, so the
# check is repeated against their parameter name.

GATED = [
    ("/translate", {"text": "hello", "target_lang": "ko"}),
    ("/translate/enhanced", {"text": "hello", "target_lang": "ko"}),
    ("/genz/explain", {"text": "no cap"}),
]


@pytest.mark.parametrize("path,_body", GATED)
def test_no_gated_endpoint_exposes_its_guard_as_a_parameter(path, _body):
    paths = client.get("/openapi.json").json()["paths"]
    for operation in paths[path].values():
        names = [p["name"] for p in operation.get("parameters", [])]
        assert "who" not in names, f"{path} exposes the allowance guard as a parameter"
        assert "_paid" not in names


@pytest.mark.parametrize("path,body", GATED)
@pytest.mark.parametrize("query", ["?who=x", "?who=user-1", "?_paid=x", "?plan=pro"])
def test_the_guard_cannot_be_satisfied_from_the_query_string(path, body, query):
    assert client.post(f"{path}{query}", json=body).status_code in (401, 402)


@pytest.mark.parametrize("path,body", GATED)
def test_the_guard_cannot_be_satisfied_from_the_body(path, body):
    assert client.post(path, json={**body, "who": "user-1", "plan": "pro"}).status_code in (
        401, 402
    )


# ── Metering fails open ──────────────────────────────────────────────────────

def test_recording_usage_never_raises(monkeypatch):
    """A metering failure must not become a user-facing error. Losing a few
    cents of accounting is always better than a caption that won't start."""
    import asyncio

    from app import usage as usage_module

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("app.supa.rest", _boom)
    asyncio.run(usage_module.record("token", "captions", 60))  # must not raise


def test_reading_usage_degrades_to_zero(monkeypatch):
    import asyncio

    from app import usage as usage_module

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("app.supa.rest", _boom)
    result = asyncio.run(usage_module.read("token"))
    assert result.totals == EMPTY
    assert result.period_end is None


def test_a_negative_or_zero_amount_is_never_recorded(monkeypatch):
    """The database refuses these too, but a client-side guard means a bug can't
    even attempt to decrement someone's meter."""
    import asyncio

    calls: list = []

    async def _rest(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("should not have been called")

    monkeypatch.setattr("app.supa.rest", _rest)
    from app import usage as usage_module

    for amount in (0, -1, -10_000):
        asyncio.run(usage_module.record("token", "captions", amount))
    asyncio.run(usage_module.record("token", "not_a_metric", 5))
    assert calls == []


# ── The subscription payload Settings renders from ───────────────────────────

def test_the_subscription_payload_carries_everything_settings_needs():
    """Settings must not hard-code a single limit — a '3 hrs' in the UI is a
    support ticket the day the cap changes here."""
    with acting_as("basic", captions=9 * 3600 + 24 * 60, translated=int(1.4 * CHARS_PER_HOUR),
                   explain=28):
        body = client.get("/billing/subscription").json()

    assert body["tier"] == "basic"
    assert body["planName"] == "Basic"
    assert body["priceUsd"] == 7.99
    assert body["periodEnd"] == "2026-09-12T00:00:00+00:00"

    captions = body["usage"]["captions"]
    assert captions["limit"] == 12 * 3600
    assert 0.77 < captions["ratio"] < 0.79
    assert captions["exhausted"] is False

    assert body["usage"]["translated"]["included"] is True
    assert body["usage"]["explain"]["used"] == 28
    assert body["usage"]["cloud_tts"]["included"] is False  # Basic has no cloud voices
    assert body["profiles"] == 4
    assert body["voiceCloning"] is False


def test_the_free_payload_reports_exclusions_rather_than_zero_limits():
    with acting_as("free"):
        body = client.get("/billing/subscription").json()
    assert body["tier"] == "free"
    assert body["paid"] is False
    assert body["usage"]["translated"]["included"] is False
    assert body["usage"]["captions"]["included"] is True
    assert body["profiles"] == 1


# ── Findings from QA round 1 ─────────────────────────────────────────────────
#
# Each of these pins a defect that was present in the first working version and
# that every test above passed straight through.

def test_the_guard_does_not_re_read_usage_on_every_request(monkeypatch):
    """QA-1: the allowance read sat on the hot path.

    Live captions translate every finalised line, so a per-request usage read
    added a PostgREST round trip *before* each translation — doubling the
    latency of the lane whose whole purpose is to be instant.
    """
    import asyncio

    from app import usage as usage_module

    reads = 0

    class _R:
        status_code = 200

        @staticmethod
        def json():
            return [{"period_start": None, "period_end": None, "caption_seconds": 0,
                     "translated_chars": 0, "explain_lookups": 0, "cloud_tts_seconds": 0}]

    async def _rest(_method, path, _token, **_kwargs):
        nonlocal reads
        if "current_usage" in path:
            reads += 1
        return _R()

    monkeypatch.setattr("app.supa.rest", _rest)
    usage_module.invalidate("hot-token")

    async def run():
        for _ in range(20):
            await usage_module.read("hot-token")

    asyncio.run(run())
    assert reads == 1, f"{reads} round trips for 20 guarded requests"


def test_spend_inside_the_cache_window_still_counts(monkeypatch):
    """The other half of that fix. Caching the snapshot without folding in local
    spend would let a burst read its own pre-burst total and sail past the cap
    for the whole window."""
    import asyncio

    from app import usage as usage_module

    class _R:
        status_code = 200

        @staticmethod
        def json():
            return [{"period_start": None, "period_end": None, "caption_seconds": 0,
                     "translated_chars": 0, "explain_lookups": 0, "cloud_tts_seconds": 0}]

    async def _rest(_method, _path, _token, **_kwargs):
        return _R()

    monkeypatch.setattr("app.supa.rest", _rest)
    usage_module.invalidate("burst-token")

    async def run():
        await usage_module.read("burst-token")
        await usage_module.record("burst-token", "translated", 5_000)
        await usage_module.record("burst-token", "translated", 3_000)
        return await usage_module.read("burst-token")  # served from cache

    assert asyncio.run(run()).used("translated") == 8_000


def test_a_failed_read_is_distinguishable_from_genuinely_zero_usage(monkeypatch):
    """QA-1: a failed read degraded to zeros, and Settings painted every meter
    empty — which reads as 'your usage was reset', not 'we couldn't check'."""
    import asyncio

    from app import usage as usage_module

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("app.supa.rest", _boom)
    usage_module.invalidate("sad-token")
    failed = asyncio.run(usage_module.read("sad-token", fresh=True))

    assert failed.totals == EMPTY
    assert failed.ok is False       # the signal that keeps Settings honest
    assert Usage(dict(EMPTY)).ok is True  # a real zero still reads as fine


def test_a_failed_read_is_not_cached(monkeypatch):
    """Otherwise one blip pins zeros in front of the real numbers for a whole
    window, and the guard silently stops guarding."""
    import asyncio

    from app import usage as usage_module

    calls = 0

    async def _boom(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("down")

    monkeypatch.setattr("app.supa.rest", _boom)
    usage_module.invalidate("blip-token")

    async def run():
        await usage_module.read("blip-token")
        await usage_module.read("blip-token")

    asyncio.run(run())
    assert calls == 2, "a failed read must not be served from cache"


def test_a_tier_with_no_stripe_price_is_reported_as_not_purchasable(monkeypatch):
    """Reported from the browser: clicking "Start 7-day trial" returned a bare
    503 because STRIPE_PRICE_BASIC was unset. The button should never have been
    offered — the catalogue now says which tiers this deployment can sell."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.delenv("STRIPE_PRICE_BASIC", raising=False)
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_456")

    body = client.get("/billing/plans").json()
    by_tier = {plan["tier"]: plan for plan in body["plans"]}

    assert by_tier["basic"]["purchasable"] is False
    assert by_tier["pro"]["purchasable"] is True
    assert body["checkoutReady"] is True  # at least one tier is sellable


def test_nothing_is_purchasable_without_a_stripe_key(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("STRIPE_PRICE_BASIC", "price_basic_123")

    body = client.get("/billing/plans").json()
    assert body["checkoutReady"] is False
    assert all(p["purchasable"] is False for p in body["plans"] if p["tier"] != "free")


def test_an_unconfigured_checkout_blames_us_not_the_user(monkeypatch):
    """The 503 reaches the user verbatim. "No Stripe price is configured for
    basic" reads like they typed something wrong; it is our misconfiguration."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake")
    monkeypatch.delenv("STRIPE_PRICE_BASIC", raising=False)

    with acting_as("free"):
        response = client.post("/billing/checkout", json={"plan": "basic"})

    assert response.status_code == 503
    detail = response.json()["detail"].lower()
    assert "our side" in detail
    assert "stripe" not in detail and "env" not in detail  # no internals leaked
