"""Which model runs the cultural pass, and what it costs to run it.

The client picks a **tier**, never a model id. That boundary is the whole point:
a request that could name its own model could name a $75/M one, and the bill
lands on us. Tiers are a short, closed list the server owns, so adding or
repricing a model is a deploy here and nothing on the client.

The numbers are measured, not quoted — 15 en↔ko utterances of real slang through
the production prompt, parser and KB grounding. `usd_per_1k` is the observed
cost of 1,000 cultural passes, which is the unit the product spends in: one
spoken sentence, one pass.

`reasoning_effort` is load-bearing rather than a tuning knob. Several models
bill thinking tokens at the completion rate and emit multiples of the answer in
them: left at its default, gemini-3.6-flash spent **92% of its output** on
reasoning, which cost 4x and ran 3x slower for the same answer.

**Why there is no third, cheaper tier.** Three sub-$0.30/1k models were measured
on the same set and all three were rejected on latency, not price:

    upstage/solar-pro4        $0.26/1k   p50 28.0s   p95 63.2s   96% localised
    qwen/qwen3.7-flash        $0.29/1k   p50 15.1s   p95 21.0s   98%, 1 failure
    deepseek/deepseek-v4-flash $0.21/1k  p50 11.2s   p95 67.0s   93%, 1 retry

They are 5x cheaper and 8-20x slower. The cultural pass never blocks a caption,
so slowness is not fatal in principle — but an explanation that lands a minute
after the sentence arrives in a conversation that has moved on, which is not a
cheaper version of the feature so much as an absent one. Recorded here so the
next person weighing "why not a budget option" has the measurements rather than
the intuition.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTier:
    key: str
    model: str
    label: str
    #: One line the user can choose on, in their terms rather than ours.
    blurb: str
    usd_per_1k: float
    p50_ms: int
    #: OpenRouter reasoning control. None leaves the model's default alone.
    reasoning_effort: str | None
    #: Share of a character's allowance this tier spends, relative to the
    #: baseline pass. Tracks the measured cost ratio, so choosing the dearer
    #: model draws down the allowance at the rate it actually costs instead of
    #: being subsidised by everyone on the cheaper one.
    cost_weight: float


TIERS: tuple[ModelTier, ...] = (
    ModelTier(
        key="balanced",
        model="google/gemini-3.6-flash",
        label="Standard",
        blurb="Fastest, lowest cost",
        usd_per_1k=1.07,
        p50_ms=1400,
        reasoning_effort="low",
        cost_weight=1.0,
    ),
    ModelTier(
        key="thorough",
        model="openai/gpt-5.4",
        label="Thorough",
        blurb="More nuance, ~4x cost",
        usd_per_1k=4.38,
        p50_ms=2300,
        reasoning_effort=None,
        cost_weight=4.0,
    ),
)

DEFAULT_TIER = "balanced"

_BY_KEY = {tier.key: tier for tier in TIERS}


def resolve(key: str | None) -> ModelTier:
    """Tier for a client-supplied key.

    An unknown key falls back to the default rather than raising: the tier is a
    preference, and refusing to translate because a stale client sent a retired
    tier name would turn a cosmetic mismatch into a broken feature.
    """
    return _BY_KEY.get((key or "").strip().lower(), _BY_KEY[DEFAULT_TIER])


def catalogue() -> list[dict]:
    """What the picker renders. Cost is per 1,000 sentences because per-million
    tokens means nothing to someone deciding whether to leave this switched on."""
    return [
        {
            "key": tier.key,
            "label": tier.label,
            "blurb": tier.blurb,
            "usdPer1k": tier.usd_per_1k,
            "p50Ms": tier.p50_ms,
            "default": tier.key == DEFAULT_TIER,
        }
        for tier in TIERS
    ]
