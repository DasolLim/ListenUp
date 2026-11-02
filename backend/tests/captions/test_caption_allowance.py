"""The caption cap, which is the one that must land softly.

Captions are the accessibility core: someone may be relying on them to follow a
medical appointment. So the rule is that the allowance blocks the *next start*
and never the session in progress, and that any failure in the metering path
lets captioning proceed rather than stopping it. These tests pin both.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.plans import PLANS
from app.routes.billing import Caller
from app.usage import EMPTY, Usage
from tests.conftest import TEST_USER

client = TestClient(app)

PERIOD_END = "2026-09-12T00:00:00+00:00"


def _who(tier: str, caption_seconds: int) -> Caller:
    totals = dict(EMPTY)
    totals["captions"] = caption_seconds
    return Caller(
        TEST_USER,
        "test-token",
        {"status": "active", "tier": tier},
        PLANS[tier],
        Usage(totals, period_start="2026-08-12T00:00:00+00:00", period_end=PERIOD_END),
    )


@pytest.fixture
def as_caller(monkeypatch):
    """Make the websocket see a specific plan and caption spend."""
    recorded: list[tuple[str, int]] = []

    def _install(tier: str, caption_seconds: int) -> list:
        who = _who(tier, caption_seconds)

        async def _record(metric, amount):
            recorded.append((metric, amount))

        who.record = _record  # type: ignore[method-assign]

        async def _caller_for_token(_token, _user_id=None):
            return who

        monkeypatch.setattr("app.routes.billing.caller_for_token", _caller_for_token)
        return recorded

    return _install


def _config(**extra) -> str:
    return json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le", "token": "t", **extra})


def _await_ready(ws) -> dict | None:
    """Read to `ready`, returning the 80% warning frame if one preceded it.

    Near the limit the socket legitimately sends `usage` before `ready`, so a
    test that hard-codes "the first frame is ready" would break whenever it
    happens to run close to a cap.
    """
    warning = None
    while True:
        message = json.loads(ws.receive_text())
        if message["type"] == "usage":
            warning = message
            continue
        assert message["type"] == "ready", message
        return warning


# ── Blocking happens at the start, never mid-session ─────────────────────────

def test_a_session_starts_normally_when_there_is_allowance_left(as_caller):
    as_caller("free", 0)
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        assert json.loads(ws.receive_text())["type"] == "ready"


def test_a_session_is_refused_once_the_caption_allowance_is_gone(as_caller):
    as_caller("free", PLANS["free"].limit("captions"))
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        message = json.loads(ws.receive_text())
    assert message["type"] == "error"
    assert message["reason"] == "limit_reached"
    # The three things a limit must say: what ran out, when it comes back, and
    # what upgrading changes.
    assert message["metric"] == "captions"
    assert message["resetsAt"] == PERIOD_END
    assert message["upgradeTo"] == "basic"


def test_the_last_second_of_allowance_still_opens_a_session(as_caller):
    """Proves the block fires for the right reason rather than always."""
    as_caller("free", PLANS["free"].limit("captions") - 1)
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        # One second left is still allowance, so the session opens — after the
        # 80% warning, which at this point is well overdue.
        assert _await_ready(ws) is not None


def test_an_over_limit_session_that_already_started_is_never_interrupted(as_caller):
    """The heart of the rule. The allowance is read once, at connect; there is
    no mid-session re-check that could cut someone off mid-sentence."""
    recorded = as_caller("free", PLANS["free"].limit("captions") - 1)
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config(fixture="family"))
        _await_ready(ws)
        ws.send_text(json.dumps({"type": "stop"}))
        # Drain to completion — no error frame may appear part-way through.
        while True:
            message = json.loads(ws.receive_text())
            assert message["type"] != "error", "a running session was cut off"
            if message["type"] == "done":
                break
    assert recorded, "the session should still have been metered on close"


# ── The 80% warning ──────────────────────────────────────────────────────────

def test_a_session_past_eighty_percent_warns_once_at_the_start(as_caller):
    limit = PLANS["basic"].limit("captions")
    as_caller("basic", int(limit * 0.85))
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        # Captioning proceeds — a warning is not a refusal.
        warning = _await_ready(ws)
    assert warning is not None
    assert warning["metric"] == "captions"
    assert warning["remaining"] == limit - int(limit * 0.85)
    assert warning["resetsAt"] == PERIOD_END


def test_no_warning_below_the_threshold(as_caller):
    as_caller("basic", int(PLANS["basic"].limit("captions") * 0.5))
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        assert _await_ready(ws) is None


# ── Metering ─────────────────────────────────────────────────────────────────

def test_a_completed_session_is_metered_in_caption_seconds(as_caller):
    recorded = as_caller("basic", 0)
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config(fixture="family"))
        _await_ready(ws)
        ws.send_text(json.dumps({"type": "stop"}))
        while json.loads(ws.receive_text())["type"] != "done":
            pass
    assert [metric for metric, _ in recorded] == ["captions"]
    # At least one second: a session that opened consumed a real STT connection,
    # so sub-second sessions bill 1 rather than rounding to free.
    assert recorded[0][1] >= 1


def test_an_anonymous_session_is_neither_gated_nor_metered():
    """No token means no user to charge. Captioning still works — refusing an
    unauthenticated socket would break local development and the demo page."""
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le"}))
        assert json.loads(ws.receive_text())["type"] == "ready"


def test_a_billing_lookup_failure_does_not_stop_captions(monkeypatch):
    """If Supabase is unreachable, the session must proceed unmetered. A caption
    that won't start is a worse outcome than usage we failed to record."""

    async def _boom(_token, _user_id=None):
        raise RuntimeError("supabase is down")

    monkeypatch.setattr("app.routes.billing.caller_for_token", _boom)
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        assert json.loads(ws.receive_text())["type"] == "ready"


def test_a_rejected_session_is_not_metered(as_caller):
    """Being refused must not also cost you seconds — the clock starts only once
    captioning actually begins."""
    recorded = as_caller("free", PLANS["free"].limit("captions"))
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        assert json.loads(ws.receive_text())["type"] == "error"
    assert recorded == []
