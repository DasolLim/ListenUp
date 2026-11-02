"""The app's API must be reachable from a Capacitor WebView, and from nowhere new.

A Capacitor app does not run on the site's origin. iOS serves the bundle from
`capacitor://localhost` and Android from `https://localhost`, so `Origin` on
every request from the shipped app is one of those — and the middleware allowed
exactly one web origin. Every authenticated call would have failed CORS
preflight on the first device build, which surfaces in the console as a CORS
error and reads like a frontend bug.

Two halves here, deliberately: the pure `allowed_origins()` rules, where a test
can state a deployment's config exactly, and the assembled app, because the
rules being right is not the same claim as the middleware being wired to them.
"""

import pytest
from fastapi.testclient import TestClient

from app.cors import CAPACITOR_ORIGINS, allowed_origins
from app.main import app

client = TestClient(app)

WEB = "https://listenup.app"

#: Written out rather than taken from `CAPACITOR_ORIGINS`. Parametrising over
#: the constant under test means emptying that constant produces *zero* cases,
#: so the checks below would quietly skip instead of failing — proven by
#: mutation, which reported "1 failed, 7 passed, 2 skipped". A test that
#: disappears when the code breaks is worse than no test, because it is counted.
IOS_ORIGIN = "capacitor://localhost"
ANDROID_ORIGIN = "https://localhost"


def test_the_literals_here_match_the_constant_the_app_uses():
    """The other half of writing them out: if Capacitor ever changes a scheme,
    this fails rather than letting the two drift apart silently."""
    assert set(CAPACITOR_ORIGINS) == {IOS_ORIGIN, ANDROID_ORIGIN}


# ── The rules ────────────────────────────────────────────────────────────────


def test_the_configured_web_origin_is_allowed():
    assert WEB in allowed_origins({"FRONTEND_ORIGIN": WEB})


def test_both_capacitor_origins_are_allowed():
    """iOS and Android produce different origins from the same codebase, and a
    build that only ever ran on one of them would ship broken on the other."""
    allowed = allowed_origins({"FRONTEND_ORIGIN": WEB})
    assert "capacitor://localhost" in allowed, "iOS WebView origin missing"
    assert "https://localhost" in allowed, "Android WebView origin missing"


def test_an_unknown_origin_is_not_allowed():
    assert "https://evil.example" not in allowed_origins({"FRONTEND_ORIGIN": WEB})


def test_extra_origins_come_from_config():
    """Preview deployments get their own hostnames, and hard-coding them in
    source means a code change to review a branch."""
    allowed = allowed_origins(
        {"FRONTEND_ORIGIN": WEB, "EXTRA_CORS_ORIGINS": "https://a.dev, https://b.dev"}
    )
    assert "https://a.dev" in allowed and "https://b.dev" in allowed


def test_a_wildcard_is_refused_outright():
    """`*` would be the obvious way to make the app work, and it is the one this
    API must not take: it carries bearer tokens and biometric voice data."""
    with pytest.raises(ValueError, match=r"\*"):
        allowed_origins({"FRONTEND_ORIGIN": "*"})
    with pytest.raises(ValueError, match=r"\*"):
        allowed_origins({"FRONTEND_ORIGIN": WEB, "EXTRA_CORS_ORIGINS": "*"})


def test_origins_are_deduplicated_and_ordered():
    allowed = allowed_origins({"FRONTEND_ORIGIN": "https://localhost"})
    assert len(allowed) == len(set(allowed))


# ── The wiring ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("origin", [IOS_ORIGIN, ANDROID_ORIGIN])
def test_a_preflight_from_the_app_is_answered(origin: str):
    """The actual failure: a browser sends OPTIONS before any authenticated
    request, and a refusal here means the real request is never sent."""
    response = client.options(
        "/translate",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin
    assert "authorization" in response.headers.get("access-control-allow-headers", "").lower()


@pytest.mark.parametrize("origin", [IOS_ORIGIN, ANDROID_ORIGIN])
def test_a_real_request_from_the_app_carries_the_allow_header(origin: str):
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers.get("access-control-allow-origin") == origin


def test_an_unknown_origin_gets_no_allow_header():
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_the_websocket_upgrade_works_from_the_app_origin():
    """The second half of this task's gate.

    CORS middleware does not apply to WebSockets — browsers send no preflight
    for them — so this passes for a different reason than the checks above, and
    it is worth pinning that it passes at all. The socket is not exposed by it:
    it authenticates on a token in its first message rather than on a cookie, so
    a hostile page cannot open an authenticated session it has no token for.
    """
    with client.websocket_connect(
        "/ws/transcribe", headers={"Origin": "capacitor://localhost"}
    ) as ws:
        ws.send_json({"sampleRate": 16000, "encoding": "pcm_s16le"})
        assert ws.receive_json()["type"] == "ready"
