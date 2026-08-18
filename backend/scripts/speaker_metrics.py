"""How good is speaker identification, given ground truth.

Pure functions over a list of turns. No audio, no model, no I/O — so they can be
unit-tested against hand-built cases with known answers, which is the whole
point: a wrong metric is worse than no metric. This repo has already scored a
*correct* Korean transcript at 75% because the scorer counted `세 시` → `3시` as
an error, and spent a round of work chasing the wrong number.

Two conventions worth stating up front.

**Labels are matched to speakers optimally, not greedily.** "Speaker 2" is an
arbitrary name for a cluster; what matters is whether the clustering separated
the right turns, not what it called them. So the best one-to-one mapping between
displayed labels and true speakers is found by search, and everything is scored
against that. Assigning each label to whoever happens to hold a majority of its
turns is the obvious shortcut and it silently flatters a system that split one
person in two.

**Split and merge are reported separately, never netted.** They are not
symmetric errors. A split shows one person under two labels: annoying, visible,
and the reader can correct it. A merge puts two people under one label, which
attributes words to someone who never said them — and a reader using captions
because they cannot hear the original has no way to notice. A single number that
trades one for the other hides exactly the failure that matters.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import permutations


@dataclass(frozen=True)
class Turn:
    """One finalised caption, as the user saw it."""

    #: Ground truth: who actually spoke.
    speaker: str
    #: What the UI displayed as the speaker label ("Speaker 2", "Other").
    label: str
    #: The enrolled name shown, if any. `None` means a generic label was shown.
    name: str | None = None

    @property
    def shown(self) -> str:
        """What the reader actually saw for this turn — a name if there was one,
        otherwise the generic label. Identity churn is judged on this, because
        this is what a reader follows a conversation by."""
        return self.name or self.label


def _best_mapping(turns: Iterable[Turn]) -> dict[str, str]:
    """Label → true speaker, chosen to maximise correctly-attributed turns.

    Brute force over injective mappings. With the speaker cap at 4 + "Other" and
    a stated range of 1–5 people this is at most a few thousand permutations,
    which costs nothing and is exact — an approximation here would put a thumb
    on the scale of every number below it.
    """
    turns = list(turns)
    labels = sorted({t.label for t in turns})
    speakers = sorted({t.speaker for t in turns})
    if not labels or not speakers:
        return {}

    counts: dict[tuple[str, str], int] = {}
    for turn in turns:
        key = (turn.label, turn.speaker)
        counts[key] = counts.get(key, 0) + 1

    # Map the smaller set onto the larger so the search stays injective either way.
    best_score = -1
    best: dict[str, str] = {}
    if len(labels) <= len(speakers):
        for candidate in permutations(speakers, len(labels)):
            mapping = dict(zip(labels, candidate, strict=True))
            score = sum(counts.get((lab, spk), 0) for lab, spk in mapping.items())
            if score > best_score:
                best_score, best = score, mapping
    else:
        for candidate in permutations(labels, len(speakers)):
            mapping = {lab: spk for lab, spk in zip(candidate, speakers, strict=True)}
            score = sum(counts.get((lab, spk), 0) for lab, spk in mapping.items())
            if score > best_score:
                best_score, best = score, mapping
    return best


def confusion_rate(turns: Iterable[Turn]) -> float:
    """Fraction of turns attributed to the wrong person. The headline number.

    A turn under a label that maps to nobody counts as confused: the reader was
    shown a speaker that does not correspond to anyone in the room.
    """
    turns = list(turns)
    if not turns:
        return 0.0
    mapping = _best_mapping(turns)
    wrong = sum(1 for t in turns if mapping.get(t.label) != t.speaker)
    return wrong / len(turns)


def split_rate(turns: Iterable[Turn]) -> float:
    """Extra labels per speaker. 0.0 means nobody was fragmented.

    This is the reported bug — one person arriving as Speaker 1, 2 and 3 scores
    2.0 for that speaker.
    """
    turns = list(turns)
    if not turns:
        return 0.0
    per_speaker: dict[str, set[str]] = {}
    for turn in turns:
        per_speaker.setdefault(turn.speaker, set()).add(turn.label)
    extra = sum(len(labels) - 1 for labels in per_speaker.values())
    return extra / len(per_speaker)


def merge_count(turns: Iterable[Turn]) -> int:
    """How many displayed labels carried more than one real person.

    The dangerous error, reported as a raw count rather than a rate because the
    target is zero and a rate makes one instance look small.
    """
    per_label: dict[str, set[str]] = {}
    for turn in turns:
        per_label.setdefault(turn.label, set()).add(turn.speaker)
    return sum(1 for speakers in per_label.values() if len(speakers) > 1)


def count_error(turns: Iterable[Turn]) -> int:
    """|speakers shown − speakers present|. Signed information is lost on
    purpose: over- and under-counting are both wrong, and split/merge already
    say which direction."""
    turns = list(turns)
    return abs(len({t.label for t in turns}) - len({t.speaker for t in turns}))


def name_accuracy(turns: Iterable[Turn], enrolled: dict[str, str]) -> float | None:
    """Of the turns spoken by enrolled people, the fraction showing their name.

    `enrolled` maps true speaker id → the name they enrolled under. Returns
    None when no enrolled speaker spoke, which is different from 0.0 and must
    not be averaged with it.
    """
    relevant = [t for t in turns if t.speaker in enrolled]
    if not relevant:
        return None
    correct = sum(1 for t in relevant if t.name == enrolled[t.speaker])
    return correct / len(relevant)


def name_churn(turns: Iterable[Turn]) -> int:
    """How many times a speaker's displayed identity changed under them.

    Counted per true speaker over their own turns in order. The ideal is at most
    one change each — unnamed, then named — so anything beyond that is the
    "David, then Speaker 1, then David" flicker, which is the symptom this
    product is judged on. Every change costs, including a change back.
    """
    per_speaker: dict[str, list[str]] = {}
    for turn in turns:
        per_speaker.setdefault(turn.speaker, []).append(turn.shown)
    return sum(
        sum(1 for a, b in zip(seen, seen[1:], strict=False) if a != b)
        for seen in per_speaker.values()
    )


def turns_to_first_name(turns: Iterable[Turn], enrolled: dict[str, str]) -> dict[str, int | None]:
    """Per enrolled speaker, how many of their turns passed before their name
    appeared. `None` means it never did."""
    turns = list(turns)
    result: dict[str, int | None] = {}
    for speaker, name in enrolled.items():
        spoken = [t for t in turns if t.speaker == speaker]
        result[speaker] = next(
            (i for i, t in enumerate(spoken, start=1) if t.name == name), None
        )
    return result


def summarise(turns: Iterable[Turn], enrolled: dict[str, str] | None = None) -> dict:
    """Every metric for one session, ready to print or serialise."""
    turns = list(turns)
    enrolled = enrolled or {}
    return {
        "turns": len(turns),
        "speakers": len({t.speaker for t in turns}),
        "labels": len({t.label for t in turns}),
        "confusion_rate": round(confusion_rate(turns), 4),
        "split_rate": round(split_rate(turns), 4),
        "merge_count": merge_count(turns),
        "count_error": count_error(turns),
        "name_accuracy": (
            None if name_accuracy(turns, enrolled) is None
            else round(name_accuracy(turns, enrolled), 4)
        ),
        "name_churn": name_churn(turns),
        "turns_to_first_name": turns_to_first_name(turns, enrolled),
    }
