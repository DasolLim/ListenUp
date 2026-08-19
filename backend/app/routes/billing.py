"""Subscriptions: checkout, the customer portal, and the webhook that decides
who is entitled to what.

  GET  /billing/plans         — the tier table (public)
  POST /billing/checkout      — start a 7-day trial on a chosen plan
  POST /billing/portal        — Stripe-hosted billing management
  GET  /billing/subscription  — the caller's plan, allowances, and usage
  POST /billing/webhook       — Stripe -> our database (the source of truth)

Three rules hold this together:

1. **The webhook writes access, not the redirect.** A user can close the tab
   before Stripe returns them; the subscription exists regardless. Anything that
   grants access on the success URL eventually gives it away for free.
2. **Entitlement is read server-side, never sent by the client.** The frontend
   decides what to *show*; this decides what someone may *do*.
3. **Entitlement and allowance are one question.** "May this request proceed?"
   has two possible no's — wrong plan, or nothing left this month — and they are
   answered in the same dependency so there is only one place to forget.
"""

import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app import usage as usage_module
from app.plans import (
    PLANS,
    PRO_FIRST_MONTH_DISCOUNT,
    Plan,
    plan_for,
    public_catalogue,
)
from app.supa import rest, verify_user
from app.timing import span
from app.usage import Allowance, Usage, allowance

logger = logging.getLogger("listenup.billing")

router = APIRouter(prefix="/billing")
bearer = HTTPBearer(auto_error=False)

TRIAL_DAYS = 7
# Statuses that mean "let them in". Trialing counts — that is the point of a
# trial — and the grace on `canceled` is handled against current_period_end.
ACTIVE_STATUSES = {"trialing", "active"}

# Which env var holds the Stripe price for each sellable tier. Free is not
# sellable and has no price.
PRICE_ENV = {"basic": "STRIPE_PRICE_BASIC", "pro": "STRIPE_PRICE_PRO"}

# Copy for a metric that is metered, used when the allowance runs out.
METRIC_LABEL = {
    "captions": "Live captions",
    "translated": "Translated captions",
    "explain": "Explain a term",
    "cloud_tts": "Cloud read-aloud voices",
}


def _stripe() -> None:
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        raise HTTPException(503, "Billing isn't configured on this deployment.")
    stripe.api_key = key


def _app_url() -> str:
    return os.environ.get("APP_BASE_URL", "http://localhost:3000").rstrip("/")


def _price_id(tier: str) -> str:
    env = PRICE_ENV.get(tier)
    price = os.environ.get(env, "") if env else ""
    if not price:
        # Two audiences, one message. The user gets a sentence that tells them
        # this is our problem and not theirs — nothing they can do will make the
        # checkout open — and the log line names the exact variable to set.
        logger.error("checkout_unconfigured tier=%s missing_env=%s", tier, env)
        raise HTTPException(
            503,
            "Checkout isn't available yet — this is a setup issue on our side, "
            "not a problem with your account. Captions and everything on your "
            "current plan keep working.",
        )
    return price


def tier_for_price(price_id: str | None) -> str | None:
    """Reverse the price → tier mapping, for the webhook."""
    if not price_id:
        return None
    for tier, env in PRICE_ENV.items():
        if os.environ.get(env, "") == price_id:
            return tier
    return None


async def auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tuple[str, str]:
    if credentials is None:
        raise HTTPException(401, "Sign in to manage your subscription.")
    token = credentials.credentials
    return await verify_user(token), token


def _field(obj: Any, key: str, default: Any = None) -> Any:
    """Read a key from a Stripe object or a plain dict.

    `StripeObject` does not implement `.get()` — it raises rather than returning
    a default — so calling it on a live event blows up while the same code works
    fine against a dict fixture in tests. This reads both.
    """
    try:
        value = obj[key]
    except (KeyError, AttributeError, TypeError):
        return default
    return default if value is None else value


def _moment(value: int | None) -> str | None:
    return datetime.fromtimestamp(value, UTC).isoformat() if value else None


async def _row(token: str, user_id: str) -> dict:
    """The caller's subscription row, or an empty default."""
    response = await rest(
        "GET", "subscriptions", token, params={"user_id": f"eq.{user_id}", "select": "*"}
    )
    rows = response.json() if response.status_code == 200 else []
    return rows[0] if rows else {}


def entitled(row: dict) -> bool:
    """Whether a row grants paid access. Mirrors `has_paid_access` in migration
    0005 — kept in both places so a query and an API call never disagree."""
    status = row.get("status", "none")
    if status in ACTIVE_STATUSES:
        return True
    if status == "canceled" and row.get("current_period_end"):
        # Cancelling does not revoke the period already paid for.
        return datetime.fromisoformat(row["current_period_end"]) > datetime.now(UTC)
    return False


def plan_for_row(row: dict) -> Plan:
    """Which plan a subscription row grants right now.

    A row that is not entitled resolves to Free regardless of the tier it stores
    — a lapsed Pro subscriber is a Free user who used to be Pro, and the stored
    tier is history rather than access.

    The interesting case is an *entitled* row whose tier we don't recognise: a
    price renamed in Stripe, or `STRIPE_PRICE_*` missing from this deployment's
    env. Resolving that to Free would silently strip a paying customer of
    everything they bought, and the most likely cause is our own misconfiguration
    rather than anything they did. So it resolves to Basic — the lower paid tier,
    which is the conservative guess — and shouts about it in the log.
    """
    if not entitled(row):
        return plan_for("free")
    tier = (row.get("tier") or "").lower()
    if tier in PLANS and tier != "free":
        return PLANS[tier]
    logger.error(
        "subscription_tier_unresolved user=%s tier=%r status=%s — granting Basic; "
        "check STRIPE_PRICE_BASIC / STRIPE_PRICE_PRO match the live prices",
        row.get("user_id"), row.get("tier"), row.get("status"),
    )
    return PLANS["basic"]


# ── The caller, resolved once per request ────────────────────────────────────


class Caller:
    """Who is asking, what they're on, and what they've spent this period.

    Assembled once per request and passed to whichever allowance check the route
    needs, so a gated endpoint costs one subscription read and one usage read
    rather than one per check.
    """

    def __init__(self, user_id: str, token: str, row: dict, plan: Plan, usage: Usage) -> None:
        self.user_id = user_id
        self.token = token
        self.row = row
        self.plan = plan
        self.usage = usage

    @property
    def paid(self) -> bool:
        return self.plan.tier != "free"

    def allowance(self, metric: str) -> Allowance:
        return allowance(self.plan, self.usage, metric)

    async def record(self, metric: str, amount: int) -> None:
        await usage_module.record(self.token, metric, amount)


async def caller_for_token(token: str, user_id: str | None = None) -> Caller:
    """Build a Caller from a raw token.

    The FastAPI-free entry point, for callers that have a token but no request
    to hang a dependency off — the transcribe websocket, and any route that
    needs the plan alongside its own auth. Keeping one implementation means the
    plan a websocket sees and the plan an endpoint sees can never drift.
    """
    async with span("allowance") as perf:
        if user_id is None:
            user_id = await verify_user(token)
        row = await _row(token, user_id)
        plan = plan_for_row(row)
        usage = await usage_module.read(token)
        perf["tier"] = plan.tier
        # `ok` false means the usage read failed and we are running on zeros —
        # a blip that would otherwise be invisible in the aggregate.
        perf["usage_ok"] = usage.ok
        return Caller(user_id, token, row, plan, usage)


async def caller(user: Annotated[tuple[str, str], Depends(auth)]) -> Caller:
    user_id, token = user
    return await caller_for_token(token, user_id)


def _refusal(who: Caller, spent: Allowance) -> HTTPException:
    """402 with the three things the rule says a limit must tell you: what ran
    out, when it comes back, and what upgrading changes."""
    label = METRIC_LABEL.get(spent.metric, spent.metric)
    if not spent.included:
        upgrade = "Pro" if who.plan.tier == "basic" else "Basic"
        return HTTPException(
            402,
            {
                "reason": "not_included",
                "metric": spent.metric,
                "plan": who.plan.tier,
                "upgradeTo": upgrade.lower(),
                "message": f"{label} isn't part of {who.plan.name}. {upgrade} includes it.",
            },
        )
    resets = who.usage.period_end
    return HTTPException(
        402,
        {
            "reason": "limit_reached",
            "metric": spent.metric,
            "plan": who.plan.tier,
            "used": spent.used,
            "limit": spent.limit,
            "resetsAt": resets,
            "upgradeTo": "pro" if who.plan.tier != "pro" else None,
            "message": f"You've used all your {label.lower()} for this billing period.",
        },
    )


def requires(metric: str) -> Callable[..., Awaitable[Caller]]:
    """Dependency factory: the caller must be able to spend `metric`.

    402 rather than 403 on purpose — the client can distinguish "you need to
    upgrade" from "you may never do this", and show the right panel instead of
    an error.
    """

    async def dependency(who: Annotated[Caller, Depends(caller)]) -> Caller:
        spent = who.allowance(metric)
        if spent.blocked:
            raise _refusal(who, spent)
        return who

    return dependency


# There is deliberately no bare "is this user paid?" dependency. Every gated
# feature is either metered (use `requires(metric)`) or a plan capability read
# from the resolved plan (`who.plan.voice_cloning`, `who.plan.profiles`). A
# generic `paid_user` would look like it checked allowances while checking only
# entitlement — the kind of helper that silently un-meters an endpoint the day
# someone reaches for the shortest import.


# ── Routes ───────────────────────────────────────────────────────────────────


@router.get("/plans")
def plans() -> dict:
    """The tier table. Public: the pricing page needs it before sign-in."""
    # A tier is buyable only if this deployment has both a Stripe key and a
    # price for it. Reporting that lets the UI disable the button instead of
    # discovering the gap through a 503 on click.
    configured = bool(os.environ.get("STRIPE_SECRET_KEY"))
    purchasable = {
        tier: configured and bool(os.environ.get(env)) for tier, env in PRICE_ENV.items()
    }
    return {
        "plans": public_catalogue(purchasable),
        "checkoutReady": any(purchasable.values()),
        "trialDays": TRIAL_DAYS,
        # Only advertise the launch discount when a coupon is actually
        # configured — promising 20% off and then not applying it at checkout is
        # worse than never mentioning it.
        "proFirstMonthDiscount": (
            PRO_FIRST_MONTH_DISCOUNT if os.environ.get("STRIPE_COUPON_PRO_FIRST_MONTH") else 0
        ),
    }


@router.get("/subscription")
async def get_subscription(who: Annotated[Caller, Depends(caller)]) -> dict:
    """Plan, allowances, and usage — everything Settings needs to draw itself.

    Reads usage fresh rather than from the guard cache: here the number *is* the
    answer, and a meter that lags a session behind is worse than no meter — it
    teaches people not to trust it.
    """
    refreshed = await usage_module.read(who.token, fresh=True)
    # Only replace on a successful read. A failed one degrades to zeros, and
    # painting every meter empty would read as "your usage was reset" — a
    # stale-but-real number is far less alarming than a wrong one.
    if refreshed.ok:
        who.usage = refreshed

    metrics = {}
    for metric in ("captions", "translated", "explain", "cloud_tts"):
        spent = who.allowance(metric)
        metrics[metric] = {
            "used": spent.used,
            "limit": spent.limit,
            "included": spent.included,
            "unlimited": spent.unlimited,
            "remaining": spent.remaining,
            "ratio": round(spent.ratio, 4),
            "warning": spent.warning,
            "exhausted": spent.exhausted,
        }

    row = who.row
    return {
        "paid": who.paid,
        "tier": who.plan.tier,
        "planName": who.plan.name,
        "priceUsd": who.plan.price_usd,
        "status": row.get("status", "none"),
        "trialEndsAt": row.get("trial_ends_at"),
        "currentPeriodEnd": row.get("current_period_end"),
        # A trial is once per customer; Stripe enforces it, and the UI needs to
        # know so it can stop offering one that would silently not apply.
        "trialUsed": bool(row.get("trial_ends_at")),
        "trialDays": TRIAL_DAYS,
        "profiles": who.plan.profiles,
        "voiceCloning": who.plan.voice_cloning,
        "periodStart": who.usage.period_start,
        "periodEnd": who.usage.period_end,
        "usage": metrics,
    }


class CheckoutRequest(BaseModel):
    plan: str = "basic"


@router.post("/checkout")
async def create_checkout(
    body: CheckoutRequest, who: Annotated[Caller, Depends(caller)]
) -> dict:
    """Start the 7-day trial on the chosen plan.

    The plan is picked *before* the trial rather than after it, because Stripe
    needs to know what to charge when the trial converts. The user still gets to
    change their mind: switching plans mid-trial is a portal action, and
    cancelling before day 7 costs nothing.
    """
    # Answer the questions about *this user* before the ones about our
    # configuration. Someone who already subscribed should be told that, not
    # handed a 503 because a deployment is missing an env var.
    tier = body.plan.lower()
    if tier not in PRICE_ENV:
        raise HTTPException(400, f"Unknown plan '{body.plan}'. Choose basic or pro.")
    if who.paid:
        raise HTTPException(400, "You already have an active subscription.")

    _stripe()
    price = _price_id(tier)

    customer = who.row.get("stripe_customer_id")
    if not customer:
        customer = stripe.Customer.create(metadata={"user_id": who.user_id}).id

    # Only offer the trial to someone who has not had one. Stripe would refuse a
    # second trial anyway; asking for it produces a confusing error instead of a
    # working checkout.
    subscription_data: dict = {"metadata": {"user_id": who.user_id, "tier": tier}}
    if not who.row.get("trial_ends_at"):
        subscription_data["trial_period_days"] = TRIAL_DAYS

    session_args: dict = {
        "mode": "subscription",
        "customer": customer,
        "line_items": [{"price": price, "quantity": 1}],
        "subscription_data": subscription_data,
        # Card up front so the subscription can convert automatically when the
        # trial ends, which is what the user agreed to.
        "payment_method_collection": "always",
        "success_url": f"{_app_url()}/settings?checkout=done",
        "cancel_url": f"{_app_url()}/settings?checkout=cancelled",
        # user_id travels with the session so the webhook can attribute it even
        # if the customer record is new.
        "client_reference_id": who.user_id,
        "metadata": {"user_id": who.user_id, "tier": tier},
    }

    # Launch incentive: 20% off Pro's first month. duration=once, so it lands on
    # the first real invoice — which, with a trial, is the one after day 7.
    coupon = os.environ.get("STRIPE_COUPON_PRO_FIRST_MONTH", "")
    discounted = tier == "pro" and bool(coupon)
    if discounted:
        session_args["discounts"] = [{"coupon": coupon}]

    session = stripe.checkout.Session.create(**session_args)
    logger.info(
        "checkout_created user=%s tier=%s trial=%s discount=%s",
        who.user_id, tier, "trial_period_days" in subscription_data, discounted,
    )
    return {"url": session.url}


@router.post("/portal")
async def create_portal(who: Annotated[Caller, Depends(caller)]) -> dict:
    """Stripe's hosted portal: payment method, invoices, plan changes, cancellation.

    Deliberately not rebuilt in-app. It is weeks of UI plus PCI surface for
    something Stripe already does better, and cancellation in particular should
    never feel like it is being hidden behind our own flow.
    """
    _stripe()
    customer = who.row.get("stripe_customer_id")
    if not customer:
        raise HTTPException(400, "There's no billing account to manage yet.")
    session = stripe.billing_portal.Session.create(
        customer=customer, return_url=f"{_app_url()}/settings"
    )
    return {"url": session.url}


@router.post("/webhook")
async def webhook(request: Request) -> dict:
    """Stripe -> our database. The only writer of entitlement.

    The signature check is the security boundary: without it, anyone who knows
    the URL can POST themselves a subscription. Handlers are idempotent because
    Stripe retries and does not guarantee ordering.
    """
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "Webhooks aren't configured.")
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, signature, secret)
    except Exception as exc:  # bad signature, malformed body, replayed payload
        logger.warning("webhook_rejected error=%s", exc)
        raise HTTPException(400, "Invalid signature.") from exc

    kind = event["type"]
    obj = event["data"]["object"]

    if kind.startswith("customer.subscription."):
        await _sync_subscription(obj)
    elif kind == "checkout.session.completed" and _field(obj, "subscription"):
        _stripe()
        await _sync_subscription(stripe.Subscription.retrieve(_field(obj, "subscription")))
    else:
        logger.info("webhook_ignored type=%s", kind)

    return {"received": True}


def _tier_of(subscription: Any) -> str:
    """Which plan a Stripe subscription is on.

    Read from the price id on the subscription's line item, because that is what
    Stripe will actually bill. Checkout metadata is used only as a fallback: it
    records what we *asked* for, and if the two ever disagree the price is the
    truth.
    """
    items = _field(subscription, "items", {})
    data = _field(items, "data", []) or []
    for item in data:
        tier = tier_for_price(_field(_field(item, "price", {}), "id"))
        if tier:
            return tier
    meta_tier = (_field(_field(subscription, "metadata", {}), "tier") or "").lower()
    if meta_tier in PRICE_ENV:
        logger.warning(
            "subscription_tier_from_metadata subscription=%s tier=%s — price id did not "
            "match STRIPE_PRICE_BASIC/PRO",
            _field(subscription, "id"), meta_tier,
        )
        return meta_tier
    logger.error(
        "subscription_tier_unknown subscription=%s — defaulting to basic",
        _field(subscription, "id"),
    )
    return "basic"


async def _sync_subscription(subscription: Any) -> None:
    """Write one Stripe subscription into our table.

    Uses the service role: this is the one place that must write a row the user
    is forbidden to write themselves, and it never touches any other table.

    Typed `Any` rather than `dict` because both callers are legitimate and give
    different types: the webhook hands over a `StripeObject` off the event, and
    the checkout branch hands over a `stripe.Subscription`. Every read goes
    through `_field`, which exists exactly to span that difference — so a `dict`
    annotation was describing only one of the two real inputs.
    """
    user_id = _field(_field(subscription, "metadata", {}), "user_id")
    if not user_id:
        # Fall back to the customer's metadata for subscriptions created outside
        # our checkout (e.g. from the Stripe dashboard during testing).
        #
        # Wrapped because this is a network call inside a webhook: if it raises,
        # we return 5xx, and Stripe retries the same unattributable event on a
        # backoff for days. Logging and moving on is the correct failure — the
        # event genuinely isn't ours to apply.
        try:
            _stripe()
            customer = stripe.Customer.retrieve(_field(subscription, "customer"))
            user_id = _field(_field(customer, "metadata", {}), "user_id")
        except Exception as exc:
            logger.warning("webhook_customer_lookup_failed error=%s", exc)
            return
    if not user_id:
        logger.warning("webhook_unattributed subscription=%s", _field(subscription, "id"))
        return

    status = _field(subscription, "status", "none")
    row = {
        "user_id": user_id,
        "stripe_customer_id": _field(subscription, "customer"),
        "stripe_subscription_id": _field(subscription, "id"),
        "status": status,
        "tier": _tier_of(subscription),
        "current_period_end": _moment(_field(subscription, "current_period_end")),
        "trial_ends_at": _moment(_field(subscription, "trial_end")),
        "updated_at": datetime.now(UTC).isoformat(),
    }

    from app.supa import service_rest

    response = await service_rest(
        "POST",
        "subscriptions",
        json=row,
        headers={"Prefer": "resolution=merge-duplicates"},
    )
    if response.status_code not in (200, 201, 204):
        logger.error("subscription_sync_failed user=%s status=%s", user_id, response.status_code)
        return
    logger.info(
        "subscription_synced user=%s status=%s tier=%s", user_id, status, row["tier"]
    )
