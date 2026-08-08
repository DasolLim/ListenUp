"""The three tiers, and what each one includes.

This module is the **only** place plan limits are written down. The API sends
them to the client with every entitlement read, so Settings renders bars from
the same numbers the backend enforces — a hard-coded "3 hrs" in the UI is a
support ticket waiting for the day someone changes the cap here.

Limits are stored in the unit we can actually count at the point of spend:

  captions    seconds   — wall-clock of an open transcribe socket
  translated  characters— what Google/the LLM bill for; shown as hours
  explain     lookups   — one per /genz/explain miss
  cloud_tts   seconds   — rendered ElevenLabs audio
  profiles    count     — saved voice profiles (a ceiling, not a monthly spend)

`None` means unlimited. `0` means the tier does not include the feature at all,
which is a different thing and must read differently in the UI: "not on your
plan" rather than "you've used it up".

Why characters for translation when the UI says hours: translation is billed per
character, so that is the number that maps to cost, but "1.4 / 3 hrs" is what a
person can reason about. CHARS_PER_HOUR converts between them, and it is the
same 52,200 figure the cost model in SUBSCRIPTION.md §10 is built on — roughly
150 words per minute of continuous speech.
"""

from typing import Literal

Tier = Literal["free", "basic", "pro"]
Metric = Literal["captions", "translated", "explain", "cloud_tts"]

# One hour of continuous speech, in characters. Used only to present the
# translation allowance in hours; enforcement always compares characters.
CHARS_PER_HOUR = 52_200

# The cultural (LLM) pass costs about a fifth of what the fast Google pass costs
# for the same text — $0.21 vs $1.04 per translated hour (SUBSCRIPTION.md §10).
#
# This ratio exists because live captions send every finalised line through
# *both* lanes. Metering each at full character weight would charge a user twice
# for one translated sentence and quietly halve the advertised allowance, so the
# meter is denominated in cost rather than in raw characters: an hour of
# translated conversation stays an hour whichever lanes it happens to use.
ENHANCED_COST_RATIO = 0.2

HOUR = 3_600


class Plan:
    """A tier's price and allowances. Frozen at import; never mutated."""

    def __init__(
        self,
        tier: Tier,
        name: str,
        price_usd: float,
        *,
        captions: int | None,
        translated: int | None,
        explain: int | None,
        cloud_tts: int | None,
        profiles: int,
        voice_cloning: bool,
    ) -> None:
        self.tier = tier
        self.name = name
        self.price_usd = price_usd
        self.limits: dict[str, int | None] = {
            "captions": captions,
            "translated": translated,
            "explain": explain,
            "cloud_tts": cloud_tts,
        }
        self.profiles = profiles
        self.voice_cloning = voice_cloning

    def limit(self, metric: str) -> int | None:
        return self.limits.get(metric, 0)

    def includes(self, metric: str) -> bool:
        """False only when the tier excludes the feature outright."""
        return self.limit(metric) != 0


PLANS: dict[str, Plan] = {
    "free": Plan(
        "free",
        "Free",
        0.0,
        captions=3 * HOUR,
        translated=0,
        explain=5,
        cloud_tts=0,
        profiles=1,
        voice_cloning=False,
    ),
    "basic": Plan(
        "basic",
        "Basic",
        7.99,
        captions=12 * HOUR,
        translated=3 * CHARS_PER_HOUR,
        explain=100,
        cloud_tts=0,
        profiles=4,
        voice_cloning=False,
    ),
    "pro": Plan(
        "pro",
        "Pro",
        14.99,
        captions=36 * HOUR,
        translated=6 * CHARS_PER_HOUR,
        explain=None,  # unlimited
        cloud_tts=30 * 60,
        profiles=4,
        voice_cloning=True,
    ),
}

FREE = PLANS["free"]

# Percent off the first month of Pro. A launch incentive, applied as a Stripe
# coupon rather than a second Price so the renewal price stays honest in the
# checkout summary and on the invoice.
PRO_FIRST_MONTH_DISCOUNT = 20

# Warn here rather than at the limit. Landing softly is the whole design (see
# SUBSCRIPTION.md "the rule that matters most"): a caption cap that fires without
# warning can fire in a medical appointment.
WARN_AT = 0.8


def plan_for(tier: str | None) -> Plan:
    """Resolve a stored tier string to a Plan, defaulting to Free.

    Deliberately total: an unrecognised tier (a price renamed in Stripe, a row
    written by an older build) degrades to Free rather than raising. Failing
    closed here means a billing mishap costs someone their paid features for a
    support round-trip; failing open would mean giving Pro away to anyone whose
    row is malformed.
    """
    return PLANS.get((tier or "").lower(), FREE)


def as_hours(characters: int) -> float:
    """Translation characters → hours, for display only."""
    return characters / CHARS_PER_HOUR


def public_catalogue() -> list[dict]:
    """The tier table, for pricing UI and the plan picker."""
    return [
        {
            "tier": plan.tier,
            "name": plan.name,
            "priceUsd": plan.price_usd,
            "limits": plan.limits,
            "profiles": plan.profiles,
            "voiceCloning": plan.voice_cloning,
        }
        for plan in PLANS.values()
    ]
