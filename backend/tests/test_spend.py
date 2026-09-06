"""A global ceiling on what this deployment can spend in a day.

Per-user metering already exists and is enforced on every gated endpoint. What
does not exist is any limit on the *total*: five hundred signups on a good day,
or one script pointed at the socket, runs up an AssemblyAI bill nobody agreed
to. Streaming sessions cannot be capped at the provider, so the cap has to live
here.

Two rules shape every test below.

**It never cuts a live session.** That is the same rule the per-user allowance
already follows and for the same reason: a cap that fires mid-sentence can fire
in a medical appointment. The ceiling refuses the *next* start.

**It never breaks the product.** Accounting is not worth a caption. Every
failure inside the ledger is swallowed, and a ledger that cannot answer is
treated as "not over" — the opposite would let a Redis hiccup take captions
down, which is a far worse outcome than an overspend nobody noticed for an hour.
"""

from datetime import UTC, date, datetime

import pytest

from app.spend import USD_PER_UNIT, SpendLedger, ceiling_usd

DAY = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
NEXT_DAY = datetime(2026, 8, 19, 0, 30, tzinfo=UTC)


def ledger(ceiling: float | None = None, now: datetime = DAY) -> SpendLedger:
    return SpendLedger(ceiling_usd=ceiling, clock=lambda: now)


# ── What things cost ─────────────────────────────────────────────────────────


def test_the_rates_match_the_cost_model():
    """Pinned deliberately. These come from docs/product/SUBSCRIPTION.md §10, and a ceiling
    computed from drifted rates would refuse sessions at the wrong moment while
    looking perfectly reasonable."""
    assert USD_PER_UNIT["captions"] * 3600 == pytest.approx(0.15)
    assert USD_PER_UNIT["translated"] * 52_200 == pytest.approx(1.04, abs=0.01)
    assert USD_PER_UNIT["cloud_tts"] * 3600 == pytest.approx(6.80, abs=0.05)


def test_spend_accumulates_across_metrics():
    book = ledger()
    book.record("captions", 3600)       # $0.15
    book.record("translated", 52_200)   # $1.04
    assert book.spent_usd() == pytest.approx(1.19, abs=0.01)


# ── The ceiling ──────────────────────────────────────────────────────────────


def test_no_ceiling_configured_never_refuses():
    """Unset means off. A default ceiling would be a number nobody chose
    silently deciding when captions stop working."""
    book = ledger(ceiling=None)
    book.record("captions", 3600 * 1000)
    assert book.over_ceiling() is False


def test_under_the_ceiling_nothing_is_refused():
    book = ledger(ceiling=10.0)
    book.record("captions", 3600)  # $0.15
    assert book.over_ceiling() is False


def test_at_the_ceiling_the_next_start_is_refused():
    book = ledger(ceiling=0.15)
    book.record("captions", 3600)
    assert book.over_ceiling() is True


def test_the_ledger_resets_on_a_new_day():
    """Daily, on the UTC date, so a ceiling hit at 23:00 does not silence the
    service until someone notices."""
    clock = {"now": DAY}
    book = SpendLedger(ceiling_usd=0.15, clock=lambda: clock["now"])
    book.record("captions", 3600)
    assert book.over_ceiling() is True

    clock["now"] = NEXT_DAY
    assert book.over_ceiling() is False
    assert book.spent_usd() == 0.0


def test_the_day_is_reported_so_a_log_line_can_be_read():
    assert ledger().day() == date(2026, 8, 18)


# ── It must never break the product ──────────────────────────────────────────


def test_an_unknown_metric_is_refused_rather_than_counted_as_zero():
    """A typo'd metric silently costing nothing is unmonitored spend that looks
    monitored. The ledger is strict; the module-level wrapper is what swallows."""
    with pytest.raises(KeyError):
        ledger().record("captionz", 100)


def test_recording_through_the_safe_wrapper_never_raises():
    from app import spend

    spend.record("captionz", 100)          # unknown metric
    spend.record("captions", float("nan"))  # nonsense amount
    assert spend.over_ceiling() in (True, False)


def test_a_broken_ledger_reports_not_over(monkeypatch):
    """Fail open, deliberately. If accounting cannot answer, captions continue.
    An hour of unnoticed overspend is recoverable; a deaf user unable to follow
    a conversation because a counter broke is not."""
    from app import spend

    class Broken:
        def over_ceiling(self):
            raise RuntimeError("redis is on fire")

    monkeypatch.setattr(spend, "get_ledger", lambda: Broken())
    assert spend.over_ceiling() is False


# ── Configuration ────────────────────────────────────────────────────────────


def test_the_ceiling_comes_from_the_environment():
    assert ceiling_usd({"DAILY_SPEND_CEILING_USD": "25"}) == 25.0
    assert ceiling_usd({}) is None
    assert ceiling_usd({"DAILY_SPEND_CEILING_USD": ""}) is None


def test_an_unparseable_ceiling_is_ignored_rather_than_crashing_startup():
    """A typo in an env var must not be the reason the service will not boot —
    but it must be loud, because the operator thinks they have a cap."""
    assert ceiling_usd({"DAILY_SPEND_CEILING_USD": "twenty"}) is None


# ── Wired into the product ───────────────────────────────────────────────────

import json  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app import spend  # noqa: E402
from app.main import app  # noqa: E402
from tests.test_ws_transcribe import wav_chunks  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_ledger():
    """The ledger is a process singleton, so one test's spend would otherwise
    decide another's verdict — the same class of bug that made a TTS cache test
    pass by being served another test's entry."""
    spend.reset_ledger()
    yield
    spend.reset_ledger()


def test_a_session_records_its_cost_even_with_no_signed_in_user(monkeypatch):
    """Deliberately not gated on a caller.

    Per-user metering only runs when a token is sent, so an unauthenticated
    session is currently unmetered — and it still opens a real provider
    connection and still costs money. The global ledger is the one place that
    sees that spend, so it must not inherit the same blind spot.
    """
    monkeypatch.setenv("DAILY_SPEND_CEILING_USD", "1000")
    spend.reset_ledger()
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le"}))
        assert json.loads(ws.receive_text())["type"] == "ready"
        ws.send_text(json.dumps({"type": "stop"}))
        while json.loads(ws.receive_text())["type"] != "done":
            pass
    assert spend.get_ledger().spent_usd() > 0, "an anonymous session cost nothing"


def test_a_new_session_is_refused_over_the_ceiling(monkeypatch):
    monkeypatch.setenv("DAILY_SPEND_CEILING_USD", "0.01")
    spend.reset_ledger()
    spend.record("captions", 3600)  # $0.15, well over

    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le"}))
        message = json.loads(ws.receive_text())
    assert message["type"] == "error"
    assert message["reason"] == "service_capacity"
    # The message must not read as the user's fault. They may have hours of
    # allowance left and still be refused, so wording borrowed from the
    # per-user cap would be a lie they cannot act on.
    #
    # (The first version of this check was `"your" not in message` — a crude
    # proxy that failed on "nothing is wrong with your account", which is the
    # reassurance the copy exists to give. It now pins the substance.)
    body = message["message"].lower()
    assert "nothing is wrong with your account" in body
    for blame in ("allowance", "you have used", "your limit", "upgrade"):
        assert blame not in body, f"copy blames the user: {blame!r}"


def test_crossing_the_ceiling_mid_session_does_not_cut_the_session(monkeypatch):
    """The rule this whole feature bends around. A cap that fires mid-sentence
    can fire in a medical appointment, so a session that has started always
    finishes."""
    monkeypatch.setenv("DAILY_SPEND_CEILING_USD", "1000")
    spend.reset_ledger()
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le"}))
        assert json.loads(ws.receive_text())["type"] == "ready"

        # The deployment blows its budget while this person is mid-conversation.
        spend.record("captions", 3600 * 100_000)
        assert spend.over_ceiling() is True

        # Audio *after* the ceiling is crossed — without this the test proves
        # nothing. The first version stopped the session immediately, so a
        # deliberately injected mid-session cut in `push_audio` was never
        # reached and the mutation passed. A test that never touches the code
        # it is named for is the failure this repo keeps finding.
        for chunk in wav_chunks():
            ws.send_bytes(chunk)

        ws.send_text(json.dumps({"type": "stop"}))
        finished = False
        while True:
            message = json.loads(ws.receive_text())
            assert message.get("reason") != "service_capacity", "cut a live session"
            if message["type"] == "done":
                finished = True
                break
    assert finished, "the session did not finish normally"
