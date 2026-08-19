"""Reading and recording metered usage.

Both operations go through the security-definer RPCs from migration 0006, called
with the **caller's own token**. That keeps the service-role key confined to the
billing webhook (app/supa.py) — a user can add to their own meter and read their
own row, and can do nothing else, enforced by the database rather than by us
remembering to filter.

One deliberate choice runs through this whole module: **metering failures fail
open.** If Redis is down, or the migration hasn't been applied, or PostgREST
times out, the request proceeds unmetered and we log it loudly. The alternative
is that a monitoring blip locks a deaf user out of live captions mid-appointment
to protect a few cents of margin. That trade is not close.
"""

import logging
import time
from dataclasses import dataclass, replace

from app.plans import WARN_AT, Plan

logger = logging.getLogger("listenup.usage")

# How long a usage snapshot may be reused before it is re-read.
#
# Live captions translate every finalised line, so without this every caption
# would carry an extra PostgREST round trip *before* the translation request
# even starts — doubling the latency of a lane whose entire job is to be
# instant. Fifteen seconds keeps the hot path at roughly one read per session
# burst while bounding how far past a cap someone can get, and locally recorded
# spend is folded into the cached snapshot so a burst inside the window still
# counts.
#
# The cache is per-process, so N workers can each be up to one window stale.
# That is the same "small emergency reserve past the cap" the product already
# chooses deliberately (SUBSCRIPTION.md), not an accident.
CACHE_TTL_S = 15.0

_cache: dict[str, tuple[float, "Usage"]] = {}

# Column name in the `usage` table for each metric the plans define.
_COLUMNS = {
    "captions": "caption_seconds",
    "translated": "translated_chars",
    "explain": "explain_lookups",
    "cloud_tts": "cloud_tts_seconds",
}

EMPTY: dict[str, int] = dict.fromkeys(_COLUMNS, 0)


@dataclass(frozen=True)
class Usage:
    """One billing period's totals, plus its boundaries.

    `ok` says whether these numbers came from the database. A failed read
    degrades to zeros so guards fail open, but zeros-because-we-couldn't-ask and
    zeros-because-nothing-was-spent must stay distinguishable — otherwise a
    momentary outage silently renders every meter in Settings as empty, which
    reads as "your usage was reset" rather than "we couldn't check".
    """

    totals: dict[str, int]
    period_start: str | None = None
    period_end: str | None = None
    ok: bool = True

    def used(self, metric: str) -> int:
        return self.totals.get(metric, 0)


def _cache_key(token: str) -> str:
    # The token, not the user id: the id costs a verification round trip to
    # learn, and a token already scopes to exactly one user.
    return token


def invalidate(token: str) -> None:
    """Drop a cached snapshot — used by tests and after a plan change."""
    _cache.pop(_cache_key(token), None)


async def read(token: str, *, fresh: bool = False) -> Usage:
    """The caller's usage for the current billing period.

    Served from a short-lived per-process cache unless `fresh` is asked for.
    Pass `fresh=True` where the number is the *answer* rather than a guard — the
    Settings meters, for instance, must not show a value up to a window old.
    """
    key = _cache_key(token)
    if not fresh:
        entry = _cache.get(key)
        if entry and time.monotonic() - entry[0] < CACHE_TTL_S:
            return entry[1]

    from app.supa import rest

    try:
        response = await rest("POST", "rpc/current_usage", token, json={})
        if response.status_code != 200:
            logger.warning("usage_read_failed status=%s", response.status_code)
            return Usage(dict(EMPTY), ok=False)
        # PostgREST returns a list for a set-returning function; be tolerant of
        # a bare object in case the RPC shape changes.
        rows = response.json()
        if isinstance(rows, list):
            row = rows[0] if rows else {}
        else:
            row = rows if isinstance(rows, dict) else {}
        usage = Usage(
            totals={metric: int(row.get(column) or 0) for metric, column in _COLUMNS.items()},
            period_start=row.get("period_start"),
            period_end=row.get("period_end"),
        )
        _cache[key] = (time.monotonic(), usage)
        return usage
    except Exception as exc:  # network, missing migration, malformed row
        # Not cached: a failed read must not pin zero usage in front of a real
        # one for the whole window.
        logger.warning("usage_read_error error=%s", exc)
        return Usage(dict(EMPTY), ok=False)


async def record(token: str, metric: str, amount: int) -> None:
    """Add to a meter. Never raises — see the module docstring on failing open."""
    if amount <= 0 or metric not in _COLUMNS:
        return

    # Fold the spend into the cached snapshot immediately. Without this a burst
    # inside the cache window reads its own pre-burst total and can run well
    # past the cap before the next refresh notices.
    key = _cache_key(token)
    entry = _cache.get(key)
    if entry:
        totals = dict(entry[1].totals)
        totals[metric] = totals.get(metric, 0) + amount
        _cache[key] = (entry[0], replace(entry[1], totals=totals))

    from app.supa import rest

    try:
        response = await rest(
            "POST", "rpc/record_usage", token, json={"p_metric": metric, "p_amount": int(amount)}
        )
        if response.status_code not in (200, 204):
            logger.warning(
                "usage_record_failed metric=%s amount=%s status=%s",
                metric, amount, response.status_code,
            )
        else:
            logger.info("usage_recorded metric=%s amount=%s", metric, amount)
    except Exception as exc:
        logger.warning("usage_record_error metric=%s error=%s", metric, exc)


@dataclass(frozen=True)
class Allowance:
    """Whether one metric may be spent, and what to say if not.

    `remaining` is None for an unlimited metric. `included` distinguishes "your
    plan doesn't have this" from "you've used it up" — they need different copy
    and different buttons, and collapsing them into one boolean is how you end
    up telling a Free user they've run out of something they never had.
    """

    metric: str
    limit: int | None
    used: int
    included: bool

    @property
    def unlimited(self) -> bool:
        return self.included and self.limit is None

    @property
    def remaining(self) -> int | None:
        if not self.included:
            return 0
        if self.limit is None:
            return None
        return max(0, self.limit - self.used)

    @property
    def ratio(self) -> float:
        if not self.included:
            return 1.0
        if self.limit is None or self.limit == 0:
            return 0.0
        return min(1.0, self.used / self.limit)

    @property
    def exhausted(self) -> bool:
        return self.included and self.limit is not None and self.used >= self.limit

    @property
    def warning(self) -> bool:
        """80% — warn here, so the limit never arrives as a surprise."""
        return self.included and not self.exhausted and self.ratio >= WARN_AT

    @property
    def blocked(self) -> bool:
        return not self.included or self.exhausted


def allowance(plan: Plan, usage: Usage, metric: str) -> Allowance:
    return Allowance(
        metric=metric,
        limit=plan.limit(metric),
        used=usage.used(metric),
        included=plan.includes(metric),
    )
