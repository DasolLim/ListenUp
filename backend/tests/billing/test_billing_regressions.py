"""Adversarial QA for the three bugs found while building billing.

Each bug is tested by the thing that *would have shipped*: a request that used to
succeed, a failure mode that used to 5xx, a value shape that used to raise. A
test that only checks the happy path would have passed against every one of them.
"""

import json
import time

import pytest
import stripe
from fastapi.testclient import TestClient

from app.main import app
from app.routes.billing import _field, entitled

client = TestClient(app)
SECRET = "whsec_regression"


def _signed(payload: dict, secret: str = SECRET) -> dict:
    body = json.dumps(payload)
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(f"{ts}.{body}", secret)
    return {"content": body, "headers": {"stripe-signature": f"t={ts},v1={sig}"}}


def _event(kind: str, obj: dict) -> dict:
    return {
        "id": "evt_regression",
        "object": "event",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "type": kind,
        "livemode": False,
        "pending_webhooks": 0,
        "request": {"id": None, "idempotency_key": None},
        "data": {"object": obj},
    }


# ── Bug 1: the paywall was satisfiable from the URL ───────────────────────────
#
# `Depends` was never imported into translate.py. FastAPI could not resolve the
# annotation, silently demoted `_paid` to a query parameter, and every paid
# endpoint became free to anyone who guessed the name.

PAID_ENDPOINTS = [
    ("/translate", {"text": "hello", "target_lang": "ko"}),
    ("/translate/enhanced", {"text": "hello", "target_lang": "ko"}),
    ("/genz/explain", {"text": "no cap"}),
]


@pytest.mark.parametrize("path,body", PAID_ENDPOINTS)
def test_paid_endpoints_refuse_anonymous_callers(path, body):
    assert client.post(path, json=body).status_code in (401, 402)


@pytest.mark.parametrize("path,body", PAID_ENDPOINTS)
@pytest.mark.parametrize(
    "query",
    ["?_paid=x", "?_paid=true", "?_paid=user-1", "?_paid=", "?_PAID=x", "?paid=x"],
)
def test_the_guard_cannot_be_satisfied_from_the_query_string(path, body, query):
    """The exact shape of the original bug, across every spelling of it."""
    assert client.post(f"{path}{query}", json=body).status_code in (401, 402)


@pytest.mark.parametrize("path,body", PAID_ENDPOINTS)
def test_the_guard_cannot_be_satisfied_from_the_body(path, body):
    """A dependency demoted to a *body* field would be just as exploitable."""
    assert client.post(path, json={**body, "_paid": "user-1"}).status_code in (401, 402)


def test_paid_endpoints_declare_no_paid_parameter_in_their_schema():
    """The strongest version of this check: if the guard is ever demoted again,
    it shows up as a documented parameter named `_paid`. This catches the bug
    without needing to guess how it might be exploited."""
    paths = client.get("/openapi.json").json()["paths"]
    for path, _ in PAID_ENDPOINTS:
        for operation in paths[path].values():
            names = [p["name"] for p in operation.get("parameters", [])]
            assert "_paid" not in names, f"{path} exposes the guard as a parameter"


def test_a_bogus_bearer_token_does_not_pass():
    """Auth must actually verify, not merely require a header to exist."""
    for token in ("", "x", "Bearer", "null", "undefined"):
        response = client.post(
            "/translate",
            json={"text": "hi", "target_lang": "ko"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (401, 402), token


# ── Bug 2: an unattributable event retried forever ────────────────────────────
#
# A webhook that raises returns 5xx, and Stripe retries on a backoff for days.
# One stray event became a permanent stream of them.

MALFORMED_EVENTS = [
    ("no metadata, unknown customer",
     {"id": "sub_a", "object": "subscription", "customer": "cus_missing", "status": "active",
      "metadata": {}}),
    ("no customer at all",
     {"id": "sub_b", "object": "subscription", "status": "active", "metadata": {}}),
    ("null metadata",
     {"id": "sub_c", "object": "subscription", "customer": "cus_x", "status": "active",
      "metadata": None}),
    ("missing status",
     {"id": "sub_d", "object": "subscription", "customer": "cus_x", "metadata": {}}),
    ("empty object",
     {"object": "subscription"}),
]


@pytest.mark.parametrize("label,obj", MALFORMED_EVENTS, ids=[e[0] for e in MALFORMED_EVENTS])
def test_a_malformed_event_is_absorbed_rather_than_retried(label, obj, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    event = _event("customer.subscription.updated", obj)
    response = client.post("/billing/webhook", **_signed(event))
    assert response.status_code == 200, f"{label} would be retried by Stripe forever"


def test_an_unknown_event_type_is_absorbed(monkeypatch):
    """Stripe sends event types we never subscribed to. Ignoring them must be a
    200, not a crash."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    response = client.post("/billing/webhook", **_signed(_event("invoice.created", {"id": "in_1"})))
    assert response.status_code == 200


def test_a_replayed_event_is_still_accepted(monkeypatch):
    """Stripe retries the same event id. Handling must be idempotent — refusing
    a duplicate looks like a failure and triggers yet another retry."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    event = _event(
        "customer.subscription.deleted",
        {"id": "sub_dup", "object": "subscription", "customer": "cus_1", "status": "canceled",
         "metadata": {"user_id": "11111111-1111-1111-1111-111111111111"}},
    )
    signed = _signed(event)
    first = client.post("/billing/webhook", **signed)
    second = client.post("/billing/webhook", **signed)
    assert (first.status_code, second.status_code) == (200, 200)


# ── Bug 3: StripeObject has no .get() ─────────────────────────────────────────
#
# It raises instead of returning a default, so live events crashed on code paths
# that dict fixtures walked through happily.

def test_field_reads_a_plain_dict():
    assert _field({"a": 1}, "a") == 1
    assert _field({}, "a", "fallback") == "fallback"
    assert _field({"a": None}, "a", "fallback") == "fallback"


def test_field_reads_a_stripe_object():
    """The shape that used to raise. `StripeObject` is dict-like but raises on a
    missing key rather than returning a default."""
    from stripe import StripeObject

    obj = StripeObject.construct_from(
        {"id": "sub_1", "object": "subscription", "status": "active"}, "sk_test"
    )
    with pytest.raises(AttributeError):
        obj.get("nope")  # documents *why* the helper exists
    assert _field(obj, "status") == "active"
    assert _field(obj, "nope", "fallback") == "fallback"


def test_field_survives_values_that_are_not_containers():
    """Defensive: a malformed payload can put a scalar where an object belongs."""
    for value in (None, 3, "text", True):
        assert _field(value, "anything", "fallback") == "fallback"


def test_entitlement_never_raises_on_a_malformed_row():
    """`entitled` decides access. It must answer False rather than 500 — an
    exception here is a locked-out paying customer."""
    for row in ({}, {"status": None}, {"status": "canceled"},
                {"status": "canceled", "current_period_end": None}):
        assert entitled(row) is False


# ── Security posture: containing the service-role key ─────────────────────────
#
# The Stripe webhook is the one caller with no user JWT, so it needs a key that
# bypasses RLS. That key can otherwise read and write every table in the schema,
# including the biometric ones, so its reach is restricted in code rather than
# by convention.

def test_the_service_role_cannot_touch_biometric_tables():
    """The whole point of the RLS design is that application code cannot read
    another user's voice data. A service-role call to those tables would walk
    straight past it."""
    import asyncio

    from app.supa import service_rest

    for table in (
        "speaker_profiles",
        "speaker_embeddings",
        "consent_records",
        "custom_voices",
        "users",
        "slang_terms",
    ):
        with pytest.raises(RuntimeError, match="not permitted"):
            asyncio.run(service_rest("GET", table))


def test_the_service_role_allowlist_is_only_subscriptions():
    """A second entry here is a security decision, not a refactor. If this test
    is failing, that decision is being made — make it deliberately."""
    from app.supa import SERVICE_ROLE_TABLES

    assert set(SERVICE_ROLE_TABLES) == {"subscriptions"}


def test_the_allowlist_cannot_be_evaded_by_the_path():
    """Query strings, leading slashes and nested paths must not smuggle another
    table past the check."""
    import asyncio

    from app.supa import service_rest

    for path in (
        "speaker_profiles?select=*",
        "/speaker_profiles",
        "speaker_profiles/123",
        "speaker_embeddings?owner_user_id=eq.x",
    ):
        with pytest.raises(RuntimeError, match="not permitted"):
            asyncio.run(service_rest("GET", path))


def test_subscriptions_is_still_allowed_through():
    """Proves the guard rejects for the right reason — a check that blocked
    everything would pass the tests above vacuously."""
    import asyncio

    from app.supa import service_rest

    # Whether it succeeds depends on the environment having credentials; what
    # matters is that it is never the allowlist that stops it.
    try:
        response = asyncio.run(service_rest("GET", "subscriptions?select=user_id"))
        assert response.status_code < 500
    except RuntimeError as exc:  # the allowlist is the only RuntimeError here
        pytest.fail(f"subscriptions was blocked by the allowlist: {exc}")
    except Exception:
        pass  # missing key or no network — not the allowlist, which is the point
