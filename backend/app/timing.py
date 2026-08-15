"""Timing for the three hot paths.

Structured logging, not a metrics vendor. The point of this module is to answer
"where does the time actually go in a real session" — a question nothing in the
codebase could answer before it, which is why Korean latency had to be diagnosed
with a throwaway script against synthesised audio on one machine.

Lines are shaped for grep and for a one-line awk/jq aggregation:

    perf span=stt_window ms=812 ok=true language=ko mode=batch
    perf span=translate_rt ms=143 ok=true lane=fast cached=false chars=52
    perf span=allowance ms=2 ok=true source=cache tier=pro

Two rules hold this together:

1. **Measuring must never break the thing being measured.** Every failure inside
   this module is swallowed. A caption session must not end because a log line
   could not be formatted, and an exception raised *by the timer* would be the
   most embarrassing possible cause of an outage in an accessibility product.
2. **No I/O in the span.** The recorder does arithmetic and hands a string to the
   logging module. Anything that blocks belongs outside it, or the instrument
   changes the reading.
"""

import logging
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

logger = logging.getLogger("listenup.perf")

# Spans the codebase is allowed to emit. A fixed set rather than free strings:
# an aggregation is only useful if the names are stable, and a typo'd span is a
# metric that silently never appears.
SPANS = frozenset({"stt_window", "translate_rt", "allowance"})


def _render(name: str, ms: float, ok: bool, dims: dict[str, Any]) -> str:
    parts = [f"perf span={name}", f"ms={ms:.1f}", f"ok={str(ok).lower()}"]
    for key, value in dims.items():
        if value is None:
            continue
        # Booleans lower-cased so `ok=true` and `cached=true` read alike; spaces
        # stripped so a value can never break the key=value shape.
        rendered = str(value).lower() if isinstance(value, bool) else str(value)
        parts.append(f"{key}={rendered.replace(' ', '_')}")
    return " ".join(parts)


def record(name: str, ms: float, ok: bool = True, **dims: Any) -> None:
    """Emit one span. Never raises."""
    try:
        if name not in SPANS:
            logger.warning("perf_unknown_span name=%r", name)
            return
        logger.info("%s", _render(name, ms, ok, dims))
    except Exception:  # a broken logger must not break the caller
        pass


@asynccontextmanager
async def span(name: str, **dims: Any) -> AsyncIterator[dict[str, Any]]:
    """Time an async block.

    Yields the dimension dict so the caller can fill in what is only known once
    the work is done — whether a translation was a cache hit, how many
    characters were billed — without measuring it in two places.

        async with span("translate_rt", lane="fast") as dims:
            result = await service.translate(...)
            dims["cached"] = result.cached

    On an exception the span is still recorded, marked `ok=false`, and the
    original exception propagates untouched.
    """
    started = time.perf_counter()
    ok = True
    try:
        yield dims
    except BaseException:
        ok = False
        raise
    finally:
        record(name, (time.perf_counter() - started) * 1000, ok, **dims)


@contextmanager
def sync_span(name: str, **dims: Any) -> Iterator[dict[str, Any]]:
    """Same contract, for the synchronous call sites."""
    started = time.perf_counter()
    ok = True
    try:
        yield dims
    except BaseException:
        ok = False
        raise
    finally:
        record(name, (time.perf_counter() - started) * 1000, ok, **dims)
