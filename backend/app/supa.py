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
