"""Thin Supabase client: JWT verification + PostgREST with the USER's token.

Profile CRUD always uses the caller's own JWT so the RLS policies from
migration 0001 are the enforcement layer — the backend holds no service-role
key and cannot touch another user's biometric rows even if buggy.
"""

import os
from typing import Any

import httpx
from fastapi import HTTPException, status


def _config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get(
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", ""
    )
    if not url or not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Supabase is not configured (SUPABASE_URL / SUPABASE_ANON_KEY).",
        )
    return url, key


async def verify_user(token: str) -> str:
    """Validate an access token → internal user uuid, or 401.

    The provider (Supabase or Clerk) is chosen in `app.auth`; this signature is
    the contract every route depends on and does not change with it. Routes get
    an internal uuid either way, so the biometric tables keep `uuid` columns and
    their `on delete cascade`.
    """
    from app.auth import get_auth_provider

    return await get_auth_provider().user_id(token)


async def rest(
    method: str,
    path: str,
    token: str,
    *,
    json: Any = None,
    params: dict[str, str] | None = None,
    prefer: str | None = None,
) -> httpx.Response:
    """PostgREST request as the user (RLS applies)."""
    url, key = _config()
    headers = {"apikey": key, "Authorization": f"Bearer {token}"}
    if prefer:
        headers["Prefer"] = prefer
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.request(
            method, f"{url}/rest/v1/{path}", headers=headers, json=json, params=params
        )


# The only tables the service role may touch. The service key bypasses RLS
# entirely, so without this list its blast radius is the whole schema — every
# voice profile, embedding and consent record included.
#
# Billing is the one place that genuinely needs it: Stripe calls the webhook with
# no user session, so there is no JWT to act on behalf of, and the row being
# written is precisely the one a user must never write themselves. Everything
# else has a caller, and therefore a token, and therefore RLS.
#
# Adding a table here is a security decision. Ask whether the caller really has
# no user token before doing it.
SERVICE_ROLE_TABLES = frozenset({"subscriptions"})


async def service_rest(
    method: str,
    path: str,
    *,
    json: Any = None,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """PostgREST request with the service role — **bypasses RLS**.

    Restricted to `SERVICE_ROLE_TABLES`. The restriction is enforced rather than
    documented on purpose: a comment saying "billing only" does not survive the
    next person who needs a quick write, and the failure mode is silent — RLS
    stops protecting biometric data and nothing looks different.
    """
    table = path.split("?", 1)[0].strip("/").split("/", 1)[0]
    if table not in SERVICE_ROLE_TABLES:
        raise RuntimeError(
            f"service_rest is not permitted on '{table}'. It bypasses RLS, so it is "
            f"restricted to {sorted(SERVICE_ROLE_TABLES)}. Use rest() with the "
            f"caller's own token instead."
        )

    url, _ = _config()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "SUPABASE_SERVICE_ROLE_KEY is not set; billing webhooks cannot be recorded.",
        )
    merged = {"apikey": key, "Authorization": f"Bearer {key}", **(headers or {})}
    async with httpx.AsyncClient(timeout=15) as client:
        return await client.request(
            method, f"{url}/rest/v1/{path}", headers=merged, json=json, params=params
        )
