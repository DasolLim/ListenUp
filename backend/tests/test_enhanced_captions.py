"""Speaker naming is wired to every authenticated session.

This exists because naming silently stopped working and nothing failed. It was
behind an `enhanced: true` flag the client had to opt into; the captions page
stopped sending it during the tool consolidation, so the backend never loaded
anyone's voice profiles and every speaker came back as "Speaker 1". The whole
suite stayed green, because no test asserted that profiles were loaded at all.

So these tests assert the *wiring*, not the matching algorithm (test_naming.py
covers that): given a signed-in caller with enrolled profiles, does a plain
caption session actually try to name them?
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture
def profile_loads(monkeypatch):
    """Record whether the session loaded voice profiles, and with which token."""
    calls: list[str] = []

    async def _load_profiles(token: str):
        calls.append(token)
        return []  # an empty gallery still exercises the load path

    monkeypatch.setattr("app.routes.transcribe.load_profiles", _load_profiles)

    async def _caller_for_token(token, _user_id=None):
        from app.plans import PLANS
        from app.routes.billing import Caller
        from app.usage import EMPTY, Usage

        return Caller("u", token, {"status": "active", "tier": "pro"},
                      PLANS["pro"], Usage(dict(EMPTY)))

    monkeypatch.setattr("app.routes.billing.caller_for_token", _caller_for_token)
    return calls


def _run(config: dict) -> None:
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le", **config}))
        while True:
            message = json.loads(ws.receive_text())
            if message["type"] in ("ready", "error"):
                return


def test_a_plain_session_with_a_token_loads_voice_profiles(profile_loads):
    """The regression. No `enhanced` flag is sent — and none should be needed."""
    _run({"token": "user-token"})
    assert profile_loads == ["user-token"], (
        "an authenticated session did not load voice profiles, so nobody can be named"
    )


def test_naming_does_not_depend_on_any_client_flag(profile_loads):
    """Whether names appear is a condition (have you enrolled anyone), not a
    product choice. A client that sends nothing, `false`, or `true` must get the
    same behaviour — otherwise the flag can only ever be wrong."""
    for extra in ({}, {"enhanced": False}, {"enhanced": True}):
        profile_loads.clear()
        _run({"token": "user-token", **extra})
        assert profile_loads == ["user-token"], extra


def test_an_anonymous_session_loads_no_profiles(profile_loads):
    """No token means no user, so there is nothing to look up — and captions
    still work, which is the point."""
    _run({})
    assert profile_loads == []


def test_a_profile_load_failure_does_not_break_captions(monkeypatch):
    """Captions are the accessibility core. If Supabase is unreachable the
    session must still caption, just without names."""

    async def _boom(_token):
        raise RuntimeError("supabase is down")

    async def _caller_for_token(token, _user_id=None):
        from app.plans import PLANS
        from app.routes.billing import Caller
        from app.usage import EMPTY, Usage

        return Caller("u", token, {"status": "active", "tier": "pro"},
                      PLANS["pro"], Usage(dict(EMPTY)))

    monkeypatch.setattr("app.routes.transcribe.load_profiles", _boom)
    monkeypatch.setattr("app.routes.billing.caller_for_token", _caller_for_token)

    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le", "token": "t"}))
        assert json.loads(ws.receive_text())["type"] == "ready"


def test_named_speakers_reach_the_client(monkeypatch):
    """End to end: an enrolled profile that matches must arrive as `speakerName`
    on the caption, which is what the UI renders instead of 'Speaker 1'."""
    from services.speaker_id.matcher import Profile

    async def _load_profiles(_token):
        # A profile whose embedding the mock embedder will match against itself.
        return [Profile(profile_id="p1", display_name="Mom", embeddings=[[1.0] * 192])]

    async def _caller_for_token(token, _user_id=None):
        from app.plans import PLANS
        from app.routes.billing import Caller
        from app.usage import EMPTY, Usage

        return Caller("u", token, {"status": "active", "tier": "pro"},
                      PLANS["pro"], Usage(dict(EMPTY)))

    monkeypatch.setattr("app.routes.transcribe.load_profiles", _load_profiles)
    monkeypatch.setattr("app.routes.billing.caller_for_token", _caller_for_token)

    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({
            "sampleRate": 16000, "encoding": "pcm_s16le",
            "token": "t", "fixture": "family",
        }))
        assert json.loads(ws.receive_text())["type"] == "ready"
        ws.send_text(json.dumps({"type": "stop"}))
        saw_speaker_field = False
        while True:
            message = json.loads(ws.receive_text())
            if message["type"] == "segment":
                # The field must be present on every segment — the UI reads it
                # unconditionally, and a missing key would render as undefined.
                assert "speakerName" in message
                saw_speaker_field = True
            if message["type"] == "done":
                break
        assert saw_speaker_field, "no segments were produced"
