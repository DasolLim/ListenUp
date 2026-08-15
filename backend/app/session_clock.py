"""How long a caption session has actually been captioning.

A session is metered on wall-clock duration (`transcribe.py` records the elapsed
time once, on close) and caption lag is measured against the same origin. Both
were plain subtractions from a start timestamp, which is correct only while the
socket is always carrying audio.

Pause breaks that assumption in two directions at once:

1. **Billing.** A paused session is still connected, so a user who paused for
   five minutes to have a private conversation would be charged five minutes of
   their caption allowance for audio nobody transcribed.
2. **Telemetry.** Caption lag is `elapsed - segment.end`, where `segment.end` is
   a position in the *audio* timeline. Paused time advances the wall clock and
   not the audio, so every caption after a pause would report a lag inflated by
   the length of the pause — and `stt_window` is the series the latency work
   reads to decide where the time goes.

One clock fixes both, which is the reason this is a type rather than two
subtractions: the alternative is two places that must remember to subtract the
same thing, and the one that forgets is either a wrong bill or a wrong metric.

Deliberately not in `app/timing.py`: that module swallows every exception on
purpose, because a failed measurement must never end a session. This one decides
what a user is charged, so it gets to fail loudly instead.
"""

import time
from collections.abc import Callable


class SessionClock:
    """Elapsed session time, excluding any time spent paused.

    Monotonic, so a system clock adjustment mid-conversation cannot bill someone
    for a session that appears to run backwards.

    Pause and resume are idempotent rather than strict: they are driven by
    client messages, and a duplicate `pause` (a double tap, a retried frame)
    must not start a second interval that is never closed. Treating the repeat
    as a no-op keeps the accounting right without trusting the client to send a
    perfectly alternating sequence.
    """

    def __init__(self, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._started = now()
        self._paused_total = 0.0
        # Start of the pause currently in progress; None while running.
        self._paused_at: float | None = None

    @property
    def paused(self) -> bool:
        return self._paused_at is not None

    def pause(self) -> None:
        """Stop the clock. A no-op if it is already paused."""
        if self._paused_at is None:
            self._paused_at = self._now()

    def resume(self) -> None:
        """Restart the clock. A no-op if it is already running."""
        if self._paused_at is not None:
            self._paused_total += self._now() - self._paused_at
            self._paused_at = None

    def paused_seconds(self) -> float:
        """Total time spent paused, including a pause still in progress."""
        if self._paused_at is None:
            return self._paused_total
        return self._paused_total + (self._now() - self._paused_at)

    def elapsed(self) -> float:
        """Seconds of *captioning*, which is what the session owes and what the
        audio timeline is measured against.

        Never negative: a clock that returned a negative elapsed would turn into
        a negative usage amount, and the usage RPC rejects those outright.
        """
        return max(0.0, (self._now() - self._started) - self.paused_seconds())
