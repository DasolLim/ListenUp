"""Auth provider selection and Clerk token verification.

The security-relevant assertions here are the negative ones: a token signed by
the wrong key, an expired token, or a token with no subject must all be refused.
A permissive bug in this file is a bug that hands one user another user's
biometric data, so the forgery cases are tested explicitly rather than assumed
from "the library handles it".
"""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth import (
    ClerkAuthProvider,
    SupabaseAuthProvider,
    _email_from,
    get_auth_provider,
)

ISSUER = "https://example.clerk.accounts.dev"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


def _token(private_key, **overrides) -> str:
    claims = {
        "sub": "user_2abcDEF456ghiJKL",
        "iss": ISSUER,
        "exp": int(time.time()) + 600,
        "email": "person@example.com",
    }
    claims.update(overrides)
    for empty in [k for k, v in claims.items() if v is None]:
        del claims[empty]
    return jwt.encode(claims, private_key, algorithm="RS256")


class _Provider(ClerkAuthProvider):
    """Clerk provider with the JWKS fetch replaced by a fixed public key."""

    def __init__(self, public_key) -> None:
        super().__init__(issuer=ISSUER)
        self._public_key = public_key

    def _jwks_client(self):  # type: ignore[override]
        outer = self

        class _Client:
            def get_signing_key_from_jwt(self, _token):
                class _Key:
                    key = outer._public_key

                return _Key()

        return _Client()


# ── Provider selection ────────────────────────────────────────────────────────

def test_supabase_is_the_default_so_deploying_changes_nothing(monkeypatch):
    """The cutover must be a deliberate act, not a side effect of shipping."""
    monkeypatch.delenv("AUTH_PROVIDER", raising=False)
    get_auth_provider.cache_clear()
    assert isinstance(get_auth_provider(), SupabaseAuthProvider)
    get_auth_provider.cache_clear()


def test_clerk_is_selected_only_when_asked_for(monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDER", "clerk")
    get_auth_provider.cache_clear()
    assert isinstance(get_auth_provider(), ClerkAuthProvider)
    get_auth_provider.cache_clear()


# ── Clerk token verification ──────────────────────────────────────────────────

def test_a_validly_signed_token_yields_its_subject():
    private, public = _keypair()
    claims = _Provider(public).claims(_token(private))
    assert claims["sub"] == "user_2abcDEF456ghiJKL"


def test_a_token_signed_by_another_key_is_refused():
    """The forgery case: anyone can mint a JWT, only Clerk can sign one."""
    _, public = _keypair()
    attacker_private, _ = _keypair()
    with pytest.raises(HTTPException) as caught:
        _Provider(public).claims(_token(attacker_private))
    assert caught.value.status_code == 401


def test_an_expired_token_is_refused():
    private, public = _keypair()
    with pytest.raises(HTTPException) as caught:
        _Provider(public).claims(_token(private, exp=int(time.time()) - 60))
    assert caught.value.status_code == 401


def test_a_token_from_another_issuer_is_refused():
    """Guards against a token minted by a different Clerk instance."""
    private, public = _keypair()
    with pytest.raises(HTTPException) as caught:
        _Provider(public).claims(_token(private, iss="https://evil.example.com"))
    assert caught.value.status_code == 401


def test_a_token_without_a_subject_is_refused():
    """No subject means no identity to map — never fall through to a default."""
    private, public = _keypair()
    with pytest.raises(HTTPException) as caught:
        _Provider(public).claims(_token(private, sub=None))
    assert caught.value.status_code == 401


def test_garbage_is_refused_rather_than_crashing():
    _, public = _keypair()
    for bad in ("", "not-a-jwt", "a.b.c"):
        with pytest.raises(HTTPException) as caught:
            _Provider(public).claims(bad)
        assert caught.value.status_code == 401


def test_missing_issuer_config_is_a_503_not_a_401(monkeypatch):
    """An unconfigured server is our fault, not the user's — don't tell them
    their session is invalid when the deployment is incomplete.

    CLERK_ISSUER is cleared explicitly: passing issuer="" is falsy, so the
    constructor falls back to the environment, and this test silently stopped
    testing anything the moment a real CLERK_ISSUER appeared in .env.
    """
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    provider = ClerkAuthProvider(issuer="")
    with pytest.raises(HTTPException) as caught:
        provider.claims("whatever")
    assert caught.value.status_code == 503


# ── Email claim ───────────────────────────────────────────────────────────────

def test_email_is_read_from_any_of_clerks_claim_names():
    """Which one appears depends on the JWT template, so accept the known set."""
    assert _email_from({"email": "a@b.com"}) == "a@b.com"
    assert _email_from({"email_address": "c@d.com"}) == "c@d.com"
    assert _email_from({"primary_email_address": "e@f.com"}) == "e@f.com"


def test_absent_email_is_none_not_an_error():
    """Linking still works without it; the account is simply treated as new."""
    assert _email_from({"sub": "user_1"}) is None
    assert _email_from({"email": ""}) is None
