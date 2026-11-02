"""The timer must never be the reason something failed.

An instrument that can break the thing it measures is worse than no instrument,
and in an accessibility product a caption session ending because a log line
could not be formatted would be the most embarrassing possible outage. So the
contract asserted here is mostly about what *doesn't* happen: no raising, no
swallowing, no I/O.
"""

import asyncio
import logging

import pytest

from app.timing import SPANS, record, span, sync_span


def _lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("perf ")]


def test_a_span_records_its_duration(caplog):
    async def run():
        async with span("translate_rt", lane="fast"):
            await asyncio.sleep(0.02)

    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        asyncio.run(run())

    line = _lines(caplog)[0]
    assert "span=translate_rt" in line
    assert "lane=fast" in line
    assert "ok=true" in line
    ms = float(line.split("ms=")[1].split()[0])
    assert 15 < ms < 200, f"implausible duration: {ms}"


def test_dimensions_can_be_filled_in_after_the_work(caplog):
    """`cached` is only known once the call returns. Measuring it in a second
    place would be a second source of truth."""

    async def run():
        async with span("translate_rt", lane="fast") as dims:
            dims["cached"] = True
            dims["chars"] = 0

    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        asyncio.run(run())

    line = _lines(caplog)[0]
    assert "cached=true" in line
    assert "chars=0" in line


def test_a_failing_block_is_still_recorded_and_still_raises(caplog):
    """Slow failures are the ones worth seeing. The original exception must
    reach the caller untouched."""

    async def run():
        async with span("stt_window", language="ko"):
            raise ValueError("upstream blew up")

    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        with pytest.raises(ValueError, match="upstream blew up"):
            asyncio.run(run())

    line = _lines(caplog)[0]
    assert "ok=false" in line
    assert "language=ko" in line


def test_a_broken_logger_never_reaches_the_caller(monkeypatch):
    """The whole point. If emitting the line fails, the measured code proceeds."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("logging is down")

    monkeypatch.setattr("app.timing.logger.info", _boom)

    async def run():
        async with span("allowance"):
            return "work completed"

    # The measured work runs to completion and returns its value; only the
    # logging failed, and it failed silently.
    assert asyncio.run(run()) == "work completed"
    record("allowance", 1.0)  # the direct entry point must also survive


def test_an_unformattable_dimension_does_not_raise(monkeypatch):
    class Hostile:
        def __str__(self):
            raise RuntimeError("cannot render")

    async def run():
        async with span("allowance", tier=Hostile()):
            return 1

    asyncio.run(run())  # must not raise


def test_an_unknown_span_is_refused_rather_than_emitted(caplog):
    """A typo'd span name is a metric that silently never appears, so the set is
    fixed and a stray name is logged as a warning instead."""
    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        record("stt_windwo", 5.0)
    assert not _lines(caplog)
    assert any("perf_unknown_span" in r.getMessage() for r in caplog.records)


def test_the_span_set_is_the_three_hot_paths():
    assert SPANS == {"stt_window", "translate_rt", "allowance"}


def test_the_sync_variant_has_the_same_contract(caplog):
    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        with sync_span("allowance", tier="pro") as dims:
            dims["source"] = "cache"
    line = _lines(caplog)[0]
    assert "tier=pro" in line and "source=cache" in line

    with pytest.raises(ValueError):
        with sync_span("allowance"):
            raise ValueError("boom")


def test_none_dimensions_are_omitted_rather_than_printed(caplog):
    """`cached=None` in an aggregation is noise; absence is the signal."""
    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        record("allowance", 1.0, tier=None, source="db")
    line = _lines(caplog)[0]
    assert "tier=" not in line
    assert "source=db" in line


def test_values_with_spaces_cannot_break_the_key_value_shape(caplog):
    with caplog.at_level(logging.INFO, logger="listenup.perf"):
        record("allowance", 1.0, note="two words")
    assert "note=two_words" in _lines(caplog)[0]


# ── The spans are actually wired to the three hot paths ──────────────────────

def test_the_translate_lanes_emit_a_span(caplog):
    """Instrumentation that exists but is never called measures nothing."""
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import acting_as

    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="listenup.perf"), acting_as("pro"):
        client.post("/translate", json={"text": "hello there", "target_lang": "ko"})
        client.post("/translate/enhanced", json={"text": "hello there", "target_lang": "ko"})

    lanes = {line.split("lane=")[1].split()[0] for line in _lines(caplog) if "lane=" in line}
    assert lanes == {"fast", "enhanced"}


def test_the_allowance_resolution_emits_a_span(caplog):
    """Most calls should be cache hits (usage.py keeps a 15s snapshot). If they
    are not, that is itself the finding — which is why the span carries it."""
    import app.routes.billing as billing

    async def _row(*_args, **_kwargs):
        return {"status": "active", "tier": "pro"}

    async def _verify(_token):
        return "11111111-1111-1111-1111-111111111111"

    monkey = pytest.MonkeyPatch()
    monkey.setattr(billing, "_row", _row)
    monkey.setattr(billing, "verify_user", _verify)
    try:
        with caplog.at_level(logging.INFO, logger="listenup.perf"):
            asyncio.run(billing.caller_for_token("token"))
    finally:
        monkey.undo()

    line = next(line for line in _lines(caplog) if "span=allowance" in line)
    assert "tier=pro" in line
    assert "usage_ok=" in line
