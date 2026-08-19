"""Subscriptions: entitlement, the paywall, and the webhook.

The negative assertions carry the weight. An entitlement bug either gives the
product away or bills someone who cancelled, and the webhook is the one endpoint
on the API that a stranger can POST to — so signature rejection and "the client
cannot grant itself access" are tested explicitly rather than assumed.
"""

import json
import time
from datetime import UTC, datetime, timedelta

import stripe
from fastapi.testclient import TestClient

from app.main import app
from app.routes.billing import TRIAL_DAYS, entitled

client = TestClient(app)
SECRET = "whsec_test_secret"


def _event(kind: str, obj: dict) -> dict:
    """A full Stripe event envelope. The library rejects a partial one, so the
    fixture has to look like the real thing rather than just the payload we care
    about."""
    return {
        "id": "evt_test",
        "object": "event",
        "api_version": "2024-06-20",
        "created": int(time.time()),
        "type": kind,
        "livemode": False,
        "pending_webhooks": 0,
        "request": {"id": None, "idempotency_key": None},
        "data": {"object": obj},
    }


def _signed(payload: dict, secret: str = SECRET) -> dict:
    """A webhook request signed the way Stripe signs one."""
    body = json.dumps(payload)
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(f"{timestamp}.{body}", secret)
    return {
        "content": body,
        "headers": {"stripe-signature": f"t={timestamp},v1={signature}"},
    }


# ── Entitlement ───────────────────────────────────────────────────────────────

def test_trialing_counts_as_paid():
    """The whole point of a trial is that it works."""
    assert entitled({"status": "trialing"}) is True


def test_active_counts_as_paid():
    assert entitled({"status": "active"}) is True


def test_no_subscription_is_not_paid():
    assert entitled({}) is False
    assert entitled({"status": "none"}) is False


def test_cancelled_keeps_access_until_the_period_it_paid_for_ends():
    """Cancelling mid-month must not revoke time already bought — that reads as
    punishing someone for leaving, and it is money they already paid."""
    future = (datetime.now(UTC) + timedelta(days=5)).isoformat()
    assert entitled({"status": "canceled", "current_period_end": future}) is True


def test_cancelled_loses_access_once_the_period_is_over():
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert entitled({"status": "canceled", "current_period_end": past}) is False


def test_failed_payment_states_are_not_paid():
    """past_due and unpaid mean Stripe could not charge the card. Treating them
    as paid is how a subscription silently becomes free forever."""
    for status in ("past_due", "unpaid", "incomplete", "incomplete_expired"):
        assert entitled({"status": status}) is False, status


def test_the_trial_is_seven_days():
    assert TRIAL_DAYS == 7


# ── The paywall ───────────────────────────────────────────────────────────────

def test_translate_requires_a_subscription():
    """402, not 403: the client must be able to tell "pay for this" apart from
    "you may never do this", so it can show the paywall instead of an error."""
    response = client.post("/translate", json={"text": "hello", "target_lang": "ko"})
    assert response.status_code in (401, 402)
    # And the dependency must not be satisfiable from the URL. This regressed
    # once already: without `Depends` imported, FastAPI silently degraded the
    # guard to a query parameter, so ?_paid=anything walked straight through.
    bypass = client.post("/translate?_paid=x", json={"text": "hello", "target_lang": "ko"})
    assert bypass.status_code in (401, 402), "paywall bypassable via query string"


def test_explain_requires_a_subscription():
    response = client.post("/genz/explain", json={"text": "no cap"})
    assert response.status_code in (401, 402)


def test_the_paywall_message_says_what_to_do():
    """A locked feature must name the way out, not just refuse."""
    from tests.conftest import acting_as

    with acting_as("free"):
        response = client.post("/translate", json={"text": "hi", "target_lang": "ko"})
    assert response.status_code == 402
    detail = response.json()["detail"]
    # Structured, not a bare string: the client has to be able to tell "wrong
    # plan" from "used it up" without parsing English.
    assert detail["reason"] == "not_included"
    assert detail["upgradeTo"] in {"basic", "pro"}
    assert detail["message"]


def test_captions_are_not_behind_the_paywall():
    """Captions are the accessibility core and stay free. If this ever fails,
    the product has gated the thing it exists to provide."""
    response = client.get("/transcribe/languages")
    assert response.status_code == 200


def test_language_list_stays_public():
    """The picker needs it before anyone has paid for anything."""
    assert client.get("/translate/languages").status_code == 200


# ── Webhook: the one endpoint a stranger can POST to ──────────────────────────

def test_unsigned_webhook_is_rejected(monkeypatch):
    """Without this check, anyone who learns the URL can grant themselves a
    subscription by posting a customer.subscription.updated event."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    response = client.post("/billing/webhook", json={"type": "customer.subscription.updated"})
    assert response.status_code == 400


def test_webhook_signed_with_the_wrong_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    forged = _signed(
        _event("customer.subscription.updated", {"id": "sub_x", "object": "subscription"}),
        secret="whsec_attacker",
    )
    response = client.post("/billing/webhook", **forged)
    assert response.status_code == 400


def test_correctly_signed_webhook_is_accepted(monkeypatch):
    """Proves the rejection tests above fail for the right reason — a signature
    check that rejects everything would pass them vacuously."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    event = _event(
        "customer.subscription.deleted",
        {"id": "sub_1", "object": "subscription", "customer": "cus_1", "status": "canceled",
         "metadata": {"user_id": "11111111-1111-1111-1111-111111111111"},
         "current_period_end": None, "trial_end": None},
    )
    response = client.post("/billing/webhook", **_signed(event))
    assert response.status_code == 200
    assert response.json() == {"received": True}


def test_an_unattributable_event_is_absorbed_not_retried_forever(monkeypatch):
    """An event with no user_id and an unknown customer must not 5xx. Stripe
    retries failures on a backoff for days, so throwing here turns one stray
    event into a permanent stream of them."""
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    event = _event(
        "customer.subscription.updated",
        {"id": "sub_x", "object": "subscription", "customer": "cus_unknown",
         "status": "active", "metadata": {}},
    )
    response = client.post("/billing/webhook", **_signed(event))
    assert response.status_code == 200


def test_webhook_without_a_configured_secret_refuses_rather_than_trusting():
    """Fail closed: an unconfigured deployment must not accept unverified events."""
    import os

    saved = os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
    try:
        response = client.post("/billing/webhook", json={"type": "x"})
        assert response.status_code == 503
    finally:
        if saved is not None:
            os.environ["STRIPE_WEBHOOK_SECRET"] = saved


# ── The client cannot grant itself access ─────────────────────────────────────

def test_subscription_status_requires_auth():
    assert client.get("/billing/subscription").status_code == 401


def test_checkout_requires_auth():
    assert client.post("/billing/checkout").status_code == 401


def test_there_is_no_endpoint_to_set_your_own_subscription():
    """Entitlement is written by the webhook alone. Any route that let a client
    declare itself paid would make the paywall decorative."""
    schema = client.get("/openapi.json").json()["paths"]
    writable = sorted(p for p, ops in schema.items() if p.startswith("/billing") and "post" in ops)
    assert writable == ["/billing/checkout", "/billing/portal", "/billing/webhook"]
