"""The metrics have to be right before anything is measured with them.

A wrong metric is worse than no metric: it produces a number that looks like
evidence and points the work in the wrong direction. This repo has already lost
a round to that — a Korean scorer counted `세 시` → `3시` as an error and
reported 75% on a transcript that was correct.

So every metric is checked against hand-built cases whose answer is obvious by
inspection, including the degenerate ones.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from speaker_metrics import (  # noqa: E402
    Turn,
    confusion_rate,
    count_error,
    merge_count,
    name_accuracy,
    name_churn,
    split_rate,
    summarise,
    turns_to_first_name,
)

ENROLLED = {"david": "David", "mom": "Mom", "julie": "Julie"}


# ── Confusion ────────────────────────────────────────────────────────────────


def test_perfect_attribution_is_zero_confusion():
    turns = [
        Turn("david", "Speaker 1"),
        Turn("mom", "Speaker 2"),
        Turn("david", "Speaker 1"),
        Turn("mom", "Speaker 2"),
    ]
    assert confusion_rate(turns) == 0.0


def test_label_names_do_not_matter_only_the_grouping():
    """"Speaker 2" is an arbitrary name for a cluster. Calling David Speaker 2
    for the whole session is not an error; nothing is misattributed."""
    turns = [
        Turn("david", "Speaker 2"),
        Turn("mom", "Speaker 1"),
        Turn("david", "Speaker 2"),
    ]
    assert confusion_rate(turns) == 0.0


def test_two_people_under_one_label_is_confusion():
    turns = [Turn("david", "Speaker 1"), Turn("mom", "Speaker 1")]
    # Whichever way the single label is mapped, one of the two turns is wrong.
    assert confusion_rate(turns) == 0.5


def test_a_greedy_majority_mapping_would_flatter_a_split_but_this_does_not():
    """David split across two labels: the second label maps to nobody, so his
    turns under it are confused. A majority-vote mapping would score this 0."""
    turns = [
        Turn("david", "Speaker 1"),
        Turn("david", "Speaker 1"),
        Turn("david", "Speaker 2"),
        Turn("mom", "Speaker 3"),
    ]
    assert confusion_rate(turns) == pytest.approx(0.25)


def test_everything_wrong_is_total_confusion():
    turns = [Turn("david", "Speaker 1"), Turn("mom", "Speaker 1")]
    assert confusion_rate(turns) > 0


def test_empty_input_is_zero_not_a_crash():
    assert confusion_rate([]) == 0.0


# ── Split ────────────────────────────────────────────────────────────────────


def test_one_label_per_speaker_is_no_split():
    turns = [Turn("david", "Speaker 1"), Turn("mom", "Speaker 2")]
    assert split_rate(turns) == 0.0


def test_the_reported_bug_scores_two_extra_labels():
    """One person, three labels — David as Speaker 1, 2 and 3."""
    turns = [
        Turn("david", "Speaker 1"),
        Turn("david", "Speaker 2"),
        Turn("david", "Speaker 3"),
    ]
    assert split_rate(turns) == 2.0


def test_split_is_averaged_over_speakers():
    turns = [
        Turn("david", "Speaker 1"),
        Turn("david", "Speaker 2"),
        Turn("mom", "Speaker 3"),
    ]
    assert split_rate(turns) == 0.5  # one extra label, two speakers


def test_split_ignores_merges():
    """Two people sharing a label is a merge, not a split. Reported separately
    so one cannot mask the other."""
    turns = [Turn("david", "Speaker 1"), Turn("mom", "Speaker 1")]
    assert split_rate(turns) == 0.0


# ── Merge ────────────────────────────────────────────────────────────────────


def test_no_merge_when_labels_are_clean():
    assert merge_count([Turn("david", "Speaker 1"), Turn("mom", "Speaker 2")]) == 0


def test_a_shared_label_is_one_merge():
    assert merge_count([Turn("david", "Speaker 1"), Turn("mom", "Speaker 1")]) == 1


def test_two_shared_labels_are_two_merges():
    turns = [
        Turn("david", "Speaker 1"), Turn("mom", "Speaker 1"),
        Turn("julie", "Speaker 2"), Turn("david", "Speaker 2"),
    ]
    assert merge_count(turns) == 2


def test_a_split_is_not_counted_as_a_merge():
    turns = [Turn("david", "Speaker 1"), Turn("david", "Speaker 2")]
    assert merge_count(turns) == 0


# ── Count ────────────────────────────────────────────────────────────────────


def test_count_error_is_zero_when_the_number_is_right():
    assert count_error([Turn("david", "Speaker 1"), Turn("mom", "Speaker 2")]) == 0


def test_over_and_under_counting_both_register():
    assert count_error([Turn("david", "Speaker 1"), Turn("david", "Speaker 2")]) == 1
    assert count_error([Turn("david", "Speaker 1"), Turn("mom", "Speaker 1")]) == 1


# ── Naming ───────────────────────────────────────────────────────────────────


def test_name_accuracy_counts_only_enrolled_speakers():
    turns = [
        Turn("david", "Speaker 1", "David"),
        Turn("stranger", "Speaker 2", None),
    ]
    assert name_accuracy(turns, ENROLLED) == 1.0


def test_a_generic_label_for_an_enrolled_speaker_is_a_miss():
    turns = [Turn("david", "Speaker 1", "David"), Turn("david", "Speaker 1", None)]
    assert name_accuracy(turns, ENROLLED) == 0.5


def test_the_wrong_name_is_also_a_miss():
    turns = [Turn("david", "Speaker 1", "Mom")]
    assert name_accuracy(turns, ENROLLED) == 0.0


def test_no_enrolled_speaker_present_is_none_not_zero():
    """None and 0.0 mean different things and must not be averaged together."""
    assert name_accuracy([Turn("stranger", "Speaker 1")], ENROLLED) is None


# ── Churn — the symptom this product is judged on ────────────────────────────


def test_a_stable_identity_has_no_churn():
    turns = [Turn("david", "Speaker 1", "David")] * 5
    assert name_churn(turns) == 0


def test_becoming_named_once_costs_one():
    """Unnamed then named is the expected, acceptable transition."""
    turns = [Turn("david", "Speaker 1"), Turn("david", "Speaker 1", "David")]
    assert name_churn(turns) == 1


def test_the_reported_flicker_costs_two():
    """David, Speaker 1, David — the exact symptom."""
    turns = [
        Turn("david", "Speaker 1", "David"),
        Turn("david", "Speaker 1", None),
        Turn("david", "Speaker 1", "David"),
    ]
    assert name_churn(turns) == 2


def test_churn_is_counted_per_speaker_not_across_the_conversation():
    """Alternating speakers is a normal conversation, not churn."""
    turns = [
        Turn("david", "Speaker 1", "David"),
        Turn("mom", "Speaker 2", "Mom"),
        Turn("david", "Speaker 1", "David"),
        Turn("mom", "Speaker 2", "Mom"),
    ]
    assert name_churn(turns) == 0


def test_a_label_change_is_churn_even_without_names():
    turns = [Turn("david", "Speaker 1"), Turn("david", "Speaker 2")]
    assert name_churn(turns) == 1


# ── Time to name ─────────────────────────────────────────────────────────────


def test_first_name_is_reported_in_that_speakers_own_turns():
    turns = [
        Turn("david", "Speaker 1"),
        Turn("mom", "Speaker 2", "Mom"),
        Turn("david", "Speaker 1", "David"),
    ]
    assert turns_to_first_name(turns, ENROLLED)["david"] == 2
    assert turns_to_first_name(turns, ENROLLED)["mom"] == 1


def test_never_named_is_none():
    turns = [Turn("david", "Speaker 1")]
    assert turns_to_first_name(turns, ENROLLED)["david"] is None


# ── Summary ──────────────────────────────────────────────────────────────────


def test_summary_of_a_perfect_session():
    turns = [
        Turn("david", "Speaker 1", "David"),
        Turn("mom", "Speaker 2", "Mom"),
        Turn("david", "Speaker 1", "David"),
    ]
    result = summarise(turns, ENROLLED)
    assert result["confusion_rate"] == 0.0
    assert result["split_rate"] == 0.0
    assert result["merge_count"] == 0
    assert result["count_error"] == 0
    assert result["name_churn"] == 0
    assert result["name_accuracy"] == 1.0


def test_summary_of_the_reported_session():
    """David alone, fragmented across three labels and losing his name."""
    turns = [
        Turn("david", "Speaker 1", "David"),
        Turn("david", "Speaker 2", None),
        Turn("david", "Speaker 3", None),
    ]
    result = summarise(turns, ENROLLED)
    assert result["split_rate"] == 2.0
    assert result["merge_count"] == 0, "a split must never be reported as a merge"
    # "David" -> "Speaker 2" -> "Speaker 3" is two changes, not one: the reader
    # was shown three different identities for one person.
    assert result["name_churn"] == 2
    # `summarise` rounds for readable output, so compare at that precision.
    assert result["name_accuracy"] == pytest.approx(1 / 3, abs=1e-4)


def test_summary_survives_an_empty_session():
    result = summarise([], ENROLLED)
    assert result["turns"] == 0 and result["merge_count"] == 0
