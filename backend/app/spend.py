"""A ceiling on what this deployment can spend in a day.

Per-user allowances are enforced on every gated endpoint (`requires(metric)`),
so no single account can run away. There is no limit on the **total**: five
hundred signups on a good day, or one script pointed at the transcription
socket, produces a provider bill nobody agreed to. A streaming session cannot be
capped at the provider, so the cap has to live here.

Two rules, both inherited from how the per-user allowance already behaves.

**It refuses the next start, never a live session.** A cap that fires
mid-sentence can fire in a medical appointment. `CaptionSession` already makes
this trade for the per-user allowance and this follows it.

**It never breaks the product.** Accounting is not worth a caption. Every
failure inside this module is swallowed by the module-level wrappers, and a
ledger that cannot answer reports "not over" — the opposite would let a counter
bug take captions down, which is far worse than an overspend nobody noticed for
an hour.

**Scope: one process.** The ledger is in-memory, which is exactly right at
`numReplicas: 1` (see `backend/railway.json`) and wrong above it — two instances
would each allow the full ceiling. Sharing it needs Redis and a story for what
happens when Redis is down; until there is a second replica that is speculative
work. `infra/README.md` says to divide the ceiling if you scale out.
"""

import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime

logger = logging.getLogger("listenup.spend")

#: Dollars per unit, in the units the app already meters in. Sourced from
#: docs/product/SUBSCRIPTION.md §10 and pinned by a test: a ceiling computed from drifted
#: rates would refuse sessions at the wrong moment while looking reasonable.
USD_PER_UNIT: dict[str, float] = {
    # $0.15 per hour of open transcription socket (AssemblyAI).
    "captions": 0.15 / 3600,
    # $1.04 per translated hour, where an hour of speech is CHARS_PER_HOUR
    # (52,200) characters. The metered amount is already cost-weighted across
    # the two translation lanes, so this single rate covers both.
    "translated": 1.04 / 52_200,
    # ~$6.80 per hour of rendered ElevenLabs audio.
    "cloud_tts": 6.80 / 3600,
}


def ceiling_usd(env: Mapping[str, str]) -> float | None:
    """The configured daily ceiling, or None for "no ceiling".

    Unset means off. A default here would be a number nobody chose silently
    deciding when captions stop working — and for an accessibility tool that is
    not a decision to make on someone's behalf.
    """
    raw = (env.get("DAILY_SPEND_CEILING_USD") or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        # Loud, but not fatal: a typo must not be the reason the service will
        # not boot. It must be noisy because the operator believes they have a
        # cap and does not.
        logger.error(
            "spend_ceiling_unparseable value=%r — running with NO daily ceiling", raw
        )
        return None


class SpendLedger:
    """What has been spent today, and whether that is too much."""

    def __init__(
        self,
        ceiling_usd: float | None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ceiling = ceiling_usd
        self._clock = clock
        self._day = self._today()
        self._spent = 0.0

    def _today(self) -> date:
        return self._clock().astimezone(UTC).date()

    def _roll(self) -> None:
        """Reset on a new UTC day, so a ceiling hit at 23:00 does not silence
        the service until somebody notices."""
        today = self._today()
        if today != self._day:
            logger.info("spend_day_rolled from=%s spent=%.2f", self._day, self._spent)
            self._day = today
            self._spent = 0.0

    def day(self) -> date:
        self._roll()
        return self._day

    def record(self, metric: str, units: float) -> None:
        """Add spend. Raises on an unknown metric — see the module note: a
        typo'd metric costing nothing looks monitored and is not."""
        rate = USD_PER_UNIT[metric]
        self._roll()
        self._spent += rate * float(units)

    def spent_usd(self) -> float:
        self._roll()
        return self._spent

    def over_ceiling(self) -> bool:
        if self._ceiling is None:
            return False
        return self.spent_usd() >= self._ceiling


_ledger: SpendLedger | None = None
#: Day -> whether the operator has already been alerted for it.
_alerted: dict[date, bool] = {}


def get_ledger() -> SpendLedger:
    global _ledger
    if _ledger is None:
        _ledger = SpendLedger(ceiling_usd=ceiling_usd(os.environ))
    return _ledger


def reset_ledger() -> None:
    """Tests only — the ledger is a process singleton."""
    global _ledger
    _ledger = None
    _alerted.clear()


def record(metric: str, units: float) -> None:
    """Record spend. Never raises: accounting must not be able to break a call
    it is only observing."""
    try:
        get_ledger().record(metric, units)
    except Exception as exc:
        logger.warning("spend_record_failed metric=%s error=%s", metric, exc)


def over_ceiling() -> bool:
    """Is this deployment over its daily ceiling? Fails **open**."""
    try:
        over = get_ledger().over_ceiling()
    except Exception as exc:
        logger.warning("spend_check_failed error=%s", exc)
        return False
    if over and not _alerted.get(get_ledger().day()):
        # Once per day, not once per refused session: an alert that fires on
        # every attempt buries itself.
        _alerted[get_ledger().day()] = True
        logger.error(
            "spend_ceiling_reached spent=%.2f — refusing new sessions until UTC midnight",
            get_ledger().spent_usd(),
        )
        try:
            import sentry_sdk

            sentry_sdk.capture_message(
                f"Daily spend ceiling reached: ${get_ledger().spent_usd():.2f}. "
                "New caption sessions are being refused.",
                level="error",
            )
        except Exception:  # never let telemetry break the check it decorates
            pass
    return over
