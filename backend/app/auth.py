"""Who is calling — one choke point, two providers.

`verify_user()` is the only place the backend decides identity, so switching
auth provider is a change here and nowhere else. Every route keeps receiving the
same thing it always has: an **internal user uuid**.

That return type is the whole design. Clerk subjects look like `user_2abc…` and
cannot be stored in the `uuid` columns the biometric tables use (verified:
`select 'user_2abc'::uuid` raises 22P02). Rather than retype those columns and
lose their `on delete cascade` — an erasure control, not a convenience — the
Clerk subject is mapped to an internal uuid exactly once, here, against the
`public.users` table added in migration 0004.

Providers:
  * `supabase` (default) — asks Supabase to validate its own token. One HTTP
    round trip per authenticated request.
  * `clerk` — validates the JWT locally against Clerk's JWKS. No round trip,
    which matters because this sits in front of the caption path and the budget
    is <1s mic-to-screen.

Selected with `AUTH_PROVIDER`. The default is deliberately `supabase` so that
deploying this code changes nothing until the cutover is done on purpose.
"""

import os
import time
from abc import ABC, abstractmethod
from functools import lru_cache

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import PyJWKClient

# How long a fetched JWKS stays usable. Clerk rotates signing keys; PyJWKClient
# refetches on an unknown `kid`, so this is a staleness bound, not a hard limit.
JWKS_TTL_S = 600.0
REQUEST_TIMEOUT_S = 10.0


class AuthError(HTTPException):
    """401 with a message safe to show a user."""

    def __init__(self, detail: str = "Invalid or expired session.") -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)


class AuthProvider(ABC):
    @abstractmethod
    async def user_id(self, token: str) -> str:
        """Validate `token`; return the internal user uuid, or raise AuthError."""


class SupabaseAuthProvider(AuthProvider):
    """Supabase validates its own token and its uuid *is* our internal id."""

    async def user_id(self, token: str) -> str:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get(
            "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", ""
        )
        if not url or not key:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Supabase is not configured (SUPABASE_URL / SUPABASE_ANON_KEY).",
            )
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S) as client:
            response = await client.get(
                f"{url}/auth/v1/user",
                headers={"apikey": key, "Authorization": f"Bearer {token}"},
            )
        if response.status_code != 200:
            raise AuthError()
        return str(response.json()["id"])


class ClerkAuthProvider(AuthProvider):
    """Clerk signs the session JWT; we verify it locally and map it to our uuid.

    Signature verification is done against Clerk's published JWKS rather than by
    calling Clerk on every request: it removes a network hop from the hot path,
    and a forged token fails on the signature regardless of who is reachable.
    """

    def __init__(self, issuer: str | None = None) -> None:
        self._issuer = (issuer or os.environ.get("CLERK_ISSUER", "")).rstrip("/")
        self._jwks: PyJWKClient | None = None
        self._jwks_at = 0.0

    def _jwks_client(self) -> PyJWKClient:
        if not self._issuer:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Clerk is not configured (CLERK_ISSUER).",
            )
        now = time.monotonic()
        if self._jwks is None or now - self._jwks_at > JWKS_TTL_S:
            self._jwks = PyJWKClient(f"{self._issuer}/.well-known/jwks.json")
            self._jwks_at = now
        return self._jwks

    def claims(self, token: str) -> dict:
        """Verified claims, or AuthError. Signature and expiry are both checked."""
        try:
            key = self._jwks_client().get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self._issuer,
                # Clerk session tokens carry no `aud`, so audience checking is off
                # by default. `issuer` + signature already bind the token to our
                # instance; set CLERK_AUDIENCE if a template adds one.
                audience=os.environ.get("CLERK_AUDIENCE") or None,
                options={
                    "require": ["exp", "sub"],
                    "verify_aud": bool(os.environ.get("CLERK_AUDIENCE")),
                },
            )
        except HTTPException:
            raise
        except Exception as exc:  # invalid signature, expired, malformed, JWKS down
            raise AuthError() from exc

    async def user_id(self, token: str) -> str:
        claims = self.claims(token)
        subject = str(claims.get("sub") or "")
        if not subject:
            raise AuthError()
        return await link_user(token, _email_from(claims))


def _email_from(claims: dict) -> str | None:
    """Clerk's email claim name depends on the JWT template; accept the usual ones."""
    for field in ("email", "email_address", "primary_email_address"):
        value = claims.get(field)
        if isinstance(value, str) and value:
            return value
    return None


async def link_user(token: str, email: str | None) -> str:
    """Clerk subject -> internal uuid, creating or linking the row as needed.

    Delegates to the `link_current_user` RPC (migration 0004) rather than doing
    the lookup here, for one reason: **the subject is read from the verified JWT
    inside Postgres**, not passed as an argument. A caller therefore cannot claim
    someone else's identity even if this code were wrong.

    It also keeps the property that makes this backend defensible — no
    service-role key anywhere. The RPC is `security definer` so it can write the
    identity table, but it can only ever write the *caller's own* row.
    """
    from app.supa import rest

    response = await rest("POST", "rpc/link_current_user", token, json={"p_email": email})
    if response.status_code in (200, 201):
        # PostgREST returns a bare scalar for a single-value function.
        user_id = response.json()
        if isinstance(user_id, list):
            user_id = user_id[0] if user_id else None
        if isinstance(user_id, dict):
            user_id = next(iter(user_id.values()), None)
        if user_id:
            return str(user_id)
    if response.status_code == 404:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Account linking isn't set up on this deployment yet: migration "
            "0004_clerk_auth.sql has not been applied.",
        )
    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Could not establish your account. Try signing in again.",
    )


@lru_cache(maxsize=1)
def get_auth_provider() -> AuthProvider:
    """Supabase unless AUTH_PROVIDER says otherwise, so deploying is a no-op."""
    if os.environ.get("AUTH_PROVIDER", "supabase").lower() == "clerk":
        return ClerkAuthProvider()
    return SupabaseAuthProvider()
