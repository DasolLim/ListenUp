"""Pausing holds the session open without charging for the silence.

The pause button exists so someone can stop captioning for a moment — a private
aside, a phone call, a question they don't want transcribed — and carry on with
the transcript they already have. Stopping and starting again would clear it.

Holding a socket open, though, breaks two things that were plain subtractions
from a start timestamp:

  * the session is metered on wall-clock duration, so a five-minute pause would
    cost five minutes of the user's caption allowance for audio nobody
    transcribed;
  * caption lag is `elapsed - segment.end`, and `segment.end` is a position in
    the *audio* timeline, which does not advance while paused. Every caption
    after a pause would report a lag inflated by the whole pause.

Both are covered here. Time is injected rather than slept, so a five-minute
pause costs the suite nothing and the assertions are exact instead of tolerant.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.plans import PLANS
from app.routes.billing import Caller
from app.session_clock import SessionClock
from app.usage import EMPTY, Usage
from tests.captions.test_ws_transcribe import wav_chunks
from tests.conftest import TEST_USER

client = TestClient(app)

PERIOD_END = "2026-09-12T00:00:00+00:00"


class FakeTime:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.value = 1000.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


# ── The clock itself ─────────────────────────────────────────────────────────


def test_elapsed_excludes_a_completed_pause():
    fake = FakeTime()
    clock = SessionClock(now=fake.now)
    fake.advance(10)
    clock.pause()
    fake.advance(300)
    clock.resume()
    fake.advance(5)
    assert clock.elapsed() == pytest.approx(15.0)
    assert clock.paused_seconds() == pytest.approx(300.0)


def test_elapsed_excludes_a_pause_still_in_progress():
    """Read mid-pause — which is exactly what a disconnect does."""
    fake = FakeTime()
    clock = SessionClock(now=fake.now)
    fake.advance(8)
    clock.pause()
    fake.advance(600)
    assert clock.elapsed() == pytest.approx(8.0)
    assert clock.paused_seconds() == pytest.approx(600.0)


def test_pausing_twice_does_not_restart_the_interval():
    """A double tap, or a frame the client retried, must not lose the first
    pause's start and undercount the interval."""
    fake = FakeTime()
    clock = SessionClock(now=fake.now)
    fake.advance(1)
    clock.pause()
    fake.advance(30)
    clock.pause()  # ignored: the interval is already open
    fake.advance(30)
    clock.resume()
    assert clock.paused_seconds() == pytest.approx(60.0)
    assert clock.elapsed() == pytest.approx(1.0)


def test_resuming_when_not_paused_changes_nothing():
    fake = FakeTime()
    clock = SessionClock(now=fake.now)
    fake.advance(12)
    clock.resume()
    clock.resume()
    assert clock.paused_seconds() == 0.0
    assert clock.elapsed() == pytest.approx(12.0)


def test_repeated_pauses_accumulate():
    fake = FakeTime()
    clock = SessionClock(now=fake.now)
    for _ in range(3):
        fake.advance(4)
        clock.pause()
        fake.advance(20)
        clock.resume()
    assert clock.elapsed() == pytest.approx(12.0)
    assert clock.paused_seconds() == pytest.approx(60.0)


def test_paused_reports_the_current_state():
    clock = SessionClock(now=FakeTime().now)
    assert clock.paused is False
    clock.pause()
    assert clock.paused is True
    clock.resume()
    assert clock.paused is False


def test_elapsed_is_never_negative():
    """A negative elapsed would become a negative usage amount, which the usage
    RPC rejects outright — the session would fail to meter at all."""

    class Backwards:
        def __init__(self) -> None:
            self.calls = 0

        def now(self) -> float:
            self.calls += 1
            return 100.0 - self.calls * 10

    assert SessionClock(now=Backwards().now).elapsed() == 0.0


# ── The socket ───────────────────────────────────────────────────────────────


@pytest.fixture
def fake_session_clock(monkeypatch):
    """Give the websocket a clock this test drives."""
    fake = FakeTime()
    monkeypatch.setattr(
        "app.caption_session.SessionClock", lambda: SessionClock(now=fake.now)
    )
    return fake


@pytest.fixture
def as_caller(monkeypatch):
    """A paid caller whose metered amounts are captured."""
    recorded: list[tuple[str, int]] = []

    def _install(tier: str = "pro") -> list:
        totals = dict(EMPTY)
        totals["captions"] = 0
        who = Caller(
            TEST_USER,
            "test-token",
            {"status": "active", "tier": tier},
            PLANS[tier],
            Usage(totals, period_start="2026-08-12T00:00:00+00:00", period_end=PERIOD_END),
        )

        async def _record(metric, amount):
            recorded.append((metric, amount))

        who.record = _record  # type: ignore[method-assign]

        async def _caller_for_token(_token, _user_id=None):
            return who

        monkeypatch.setattr("app.routes.billing.caller_for_token", _caller_for_token)
        return recorded

    return _install


def _config(**extra) -> str:
    return json.dumps({"sampleRate": 16000, "encoding": "pcm_s16le", **extra})


def _await(ws, wanted: str) -> dict:
    """Read until the server confirms `wanted`.

    The acknowledgement is the synchronisation point: `send_text` only queues a
    frame, so a test that advanced its clock straight afterwards would be
    measuring an interval the server had not yet entered.
    """
    while True:
        message = json.loads(ws.receive_text())
        if message["type"] == wanted:
            return message


@pytest.fixture
def spy_service(monkeypatch):
    """Count the audio chunks that actually reach the transcriber."""
    from services.assemblyai.mock import MockTranscriptionService

    class Spy(MockTranscriptionService):
        audio_calls = 0

        async def send_audio(self, chunk: bytes) -> None:
            type(self).audio_calls += 1
            await super().send_audio(chunk)

    Spy.audio_calls = 0
    monkeypatch.setattr(
        "app.caption_session.get_transcription_service", lambda _language: Spy("family")
    )
    return Spy


def test_audio_sent_while_paused_never_reaches_the_transcriber(spy_service):
    """"Paused" has to mean nothing is transcribed, not merely that the client
    stopped sending: frames already in flight when the user paused must be
    dropped too, or the button promises something the server doesn't keep."""
    chunks = wav_chunks()
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config())
        assert json.loads(ws.receive_text())["type"] == "ready"

        ws.send_text(json.dumps({"type": "pause"}))
        _await(ws, "paused")
        for chunk in chunks:
            ws.send_bytes(chunk)

        ws.send_text(json.dumps({"type": "resume"}))
        _await(ws, "resumed")
        for chunk in chunks:
            ws.send_bytes(chunk)

        ws.send_text(json.dumps({"type": "stop"}))
        while json.loads(ws.receive_text())["type"] != "done":
            pass

    # Only the post-resume half was transcribed, though twice as much was sent.
    assert spy_service.audio_calls == len(chunks)


def test_resuming_continues_the_same_session_rather_than_starting_a_new_one():
    """The whole point of pause over stop: the transcript survives it."""
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config(fixture="family"))
        assert json.loads(ws.receive_text())["type"] == "ready"

        chunks = wav_chunks()
        half = len(chunks) // 2
        for chunk in chunks[:half]:
            ws.send_bytes(chunk)

        ws.send_text(json.dumps({"type": "pause"}))
        ws.send_text(json.dumps({"type": "resume"}))
        for chunk in chunks[half:]:
            ws.send_bytes(chunk)

        ws.send_text(json.dumps({"type": "stop"}))
        messages = []
        while True:
            message = json.loads(ws.receive_text())
            if message["type"] == "done":
                break
            messages.append(message)

    finals = [m for m in messages if m["type"] == "segment" and m["isFinal"]]
    # Same session: the audio timeline runs unbroken across the pause, so the
    # turn ids keep counting up instead of restarting from zero.
    assert len(finals) > 1
    assert [m["turnId"] for m in finals] == sorted({m["turnId"] for m in finals})
    ends = [m["end"] for m in finals]
    assert ends == sorted(ends)


def test_paused_time_is_not_billed(fake_session_clock, as_caller):
    recorded = as_caller("pro")
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text(_config(token="t", fixture="family"))
        assert json.loads(ws.receive_text())["type"] == "ready"

        fake_session_clock.advance(10)
        ws.send_text(json.dumps({"type": "pause"}))
        _await(ws, "paused")
        fake_session_clock.advance(300)  # five minutes of held-open silence
        ws.send_text(json.dumps({"type": "resume"}))
        _await(ws, "resumed")
        fake_session_clock.advance(5)

        ws.send_text(json.dumps({"type": "stop"}))
        while json.loads(ws.receive_text())["type"] != "done":
            pass

    assert recorded == [("captions", 15)], "billed the pause"


def test_a_session_paused_at_disconnect_still_bills_only_the_captioned_part():
    """Nobody is obliged to resume before closing the tab."""
    fake = FakeTime()
    clock = SessionClock(now=fake.now)
    fake.advance(20)
    clock.pause()
    fake.advance(3600)
    assert max(1, round(clock.elapsed())) == 20


def test_caption_lag_telemetry_excludes_the_pause(fake_session_clock, caplog):
    """`stt_window` is the series the latency work reads. A pause must not show
    up in it as a latency regression."""
    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        with client.websocket_connect("/ws/transcribe") as ws:
            ws.send_text(_config(fixture="family"))
            assert json.loads(ws.receive_text())["type"] == "ready"

            ws.send_text(json.dumps({"type": "pause"}))
            _await(ws, "paused")
            fake_session_clock.advance(300)
            ws.send_text(json.dumps({"type": "resume"}))
            _await(ws, "resumed")

            for chunk in wav_chunks():
                ws.send_bytes(chunk)
            ws.send_text(json.dumps({"type": "stop"}))
            while json.loads(ws.receive_text())["type"] != "done":
                pass

    lags = [
        float(line.split("ms=")[1].split()[0])
        for line in (r.getMessage() for r in caplog.records)
        if line.startswith("perf span=stt_window") and "stage=caption" in line
    ]
    assert lags, "expected caption-lag spans"
    # No real time passes in this session — the only clock movement is the
    # injected pause — so every caption is "on time" and the lag clamps to ~0.
    # Counting the pause instead puts all of these near 300 000 ms, which is the
    # regression this pins: a false latency cliff in the series Task 4 reads.
    assert max(lags) < 1_000, f"pause leaked into caption lag: {lags}"
