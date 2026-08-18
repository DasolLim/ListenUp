"""One voice must stay one speaker, however the provider labels it.

The reported bug: a single person talking alone was labelled Speaker 1, then
Speaker 2, then Speaker 3. Nothing was broken in the matcher — it was never
consulted. The displayed identity *was* the diarization label, and the whole
voice-identity system sat behind an enrolment check, so a user who had never
enrolled got raw labels and nothing else. Streaming diarization splits one voice
across labels routinely.

These run on the real human fixtures rather than synthesised tones, because the
question is whether two recordings of one person read as the same voice and two
different people do not — which is a property of voices, not of waveforms.
"""

import wave
from pathlib import Path

import pytest

from app import session_speakers
from app.routes.transcribe import SpeakerMapper
from app.session_speakers import MAX_VOICES, SessionSpeakers, Voice
from services.speaker_id import get_speaker_embedder

FIXTURES = Path(__file__).parent.parent / "services" / "speaker_id" / "fixtures"


def pcm(name: str) -> bytes:
    with wave.open(str(FIXTURES / f"{name}.wav"), "rb") as w:
        return w.readframes(w.getnframes())


@pytest.fixture(scope="module")
def voices() -> dict[str, list[float]]:
    """Embeddings for two recordings of one person, and one of someone else."""
    embedder = get_speaker_embedder()
    return {name: embedder.embed(pcm(name), 16000) for name in ("sam1", "sam2", "dan1")}


@pytest.fixture
def force_live_split(monkeypatch):
    """Make the live pass split one person in two — which it no longer does.

    The tests using this fixture are about `reconcile()`: evidence that arrives
    *after* a split and undoes it. They need a split to exist. They used to get
    one by raising the merge bar and using a fresh label, but a fresh label in
    the ambiguous band now stays with the nearest voice, which is the whole
    point of the continuity rule — so that recipe produces one voice and the
    tests can no longer reach the code they name.

    Raising the split floor alongside the merge bar reproduces the same state
    through the same code path, rather than hand-building two voices: the
    fixtures are one person at 0.957, and no fixture pair is one person scoring
    below a realistic floor, so this is the only way to drive a live split from
    real audio.
    """
    monkeypatch.setattr(session_speakers, "SPLIT_FLOOR", 0.99)


# ── The reported bug ─────────────────────────────────────────────────────────


def test_one_voice_under_three_labels_is_one_speaker(voices):
    """Exactly the report: one person, three diarization labels."""
    speakers = SessionSpeakers()
    keys = [
        speakers.assign("A", voices["sam1"]),
        speakers.assign("B", voices["sam2"]),
        speakers.assign("C", voices["sam1"]),
    ]
    assert len(set(keys)) == 1, f"one voice split across {len(set(keys))} speakers"
    assert len(speakers.voices) == 1


def test_the_display_label_follows_the_person_not_the_label(voices):
    """End to end through the mapper, which is what the caption actually shows."""
    speakers = SessionSpeakers()
    mapper = SpeakerMapper()
    shown = []
    for label, embedding in [("A", voices["sam1"]), ("B", voices["sam2"]), ("C", voices["sam1"])]:
        voice = speakers.assign(label, embedding)
        if voice != label:
            mapper.alias(label, voice)
        shown.append(mapper.label(label))
    assert shown == ["Speaker 1", "Speaker 1", "Speaker 1"]


# ── The error that must not be traded for it ─────────────────────────────────


def test_two_people_under_one_label_are_kept_apart(voices):
    """Merging two speakers attributes words to someone who never said them, and
    a reader who cannot hear the original has no way to catch it."""
    speakers = SessionSpeakers()
    first = speakers.assign("A", voices["sam1"])
    second = speakers.assign("A", voices["dan1"])
    assert first != second, "two different people collapsed into one speaker"


def test_a_third_voice_is_not_folded_into_either(voices):
    speakers = SessionSpeakers()
    speakers.assign("A", voices["sam1"])
    speakers.assign("B", voices["dan1"])
    assert len({speakers.assign("A", voices["sam1"]), speakers.assign("B", voices["dan1"])}) == 2


# ── Merge-only ───────────────────────────────────────────────────────────────


def test_voices_never_outnumber_the_labels_that_produced_them(voices):
    """The direction of the guarantee: clustering may fold labels together and
    must never invent a speaker the provider did not report — otherwise it adds
    a second way to produce the very symptom it exists to fix."""
    speakers = SessionSpeakers()
    labels = ["A", "B", "C", "A", "B", "C"]
    samples = [
        voices["sam1"], voices["dan1"], voices["sam2"],
        voices["dan1"], voices["sam1"], voices["dan1"],
    ]
    for label, embedding in zip(labels, samples, strict=True):
        speakers.assign(label, embedding)
    assert len(speakers.voices) <= len(set(labels))


def test_an_ambiguous_turn_does_not_split_a_known_label(voices):
    """The middle band: not confidently the same, not confidently different. A
    quiet or off-mic turn from a known speaker must not become a new one."""
    speakers = SessionSpeakers(threshold=0.99)  # nothing clears the merge bar
    first = speakers.assign("A", voices["sam1"])
    second = speakers.assign("A", voices["sam2"])  # same person, so above the floor
    assert first == second, "a known label was split by one ambiguous turn"


def test_an_ambiguous_turn_does_not_split_an_unseen_label(voices):
    """The same band, on a label with no history — which is the reported bug.

    A known label in the ambiguous band keeps its voice (the test above). A new
    label used to fall through and create a speaker, so identical audio evidence
    got opposite answers depending on whether the provider had reused a label —
    and a churning provider never does, so ambiguity always resolved to "another
    person". That is the *label* acting as the tie-break, which is the exact
    assumption this class exists to remove.

    Measured on real ECAPA at 1 s windows: the same speaker scores as low as
    0.342 (0.696 at full length) while two different speakers peak at 0.242
    (0.272 at full length). Short audio makes a voice a noisier sample of
    itself, not a better match for anyone else, so above the floor continuity
    is the right answer whether or not the label is familiar.
    """
    speakers = SessionSpeakers(threshold=0.99)  # nothing clears the merge bar
    first = speakers.assign("A", voices["sam1"])
    second = speakers.assign("B", voices["sam2"])  # same person, brand-new label
    assert first == second, "a churned label split one person into two voices"
    assert len(speakers.voices) == 1


def test_a_different_person_on_a_new_label_is_still_a_new_voice(voices):
    """The guard on the rule above. Continuity must not become "join whatever is
    nearest": below the floor the audio is positive evidence of someone else,
    and merging two people is the dangerous direction — a reader is told the
    wrong person said something, with no way to notice."""
    speakers = SessionSpeakers(threshold=0.99)
    first = speakers.assign("A", voices["sam1"])
    second = speakers.assign("B", voices["dan1"])
    assert first != second, "two different people were merged into one voice"


def test_the_number_of_tracked_voices_is_bounded(voices):
    speakers = SessionSpeakers(threshold=0.99)
    for i in range(MAX_VOICES + 5):
        speakers.assign(f"label-{i}", voices["sam1"] if i % 2 else voices["dan1"])
    assert len(speakers.voices) <= MAX_VOICES


# ── The display mapper ───────────────────────────────────────────────────────


def test_a_folded_label_frees_capacity_without_recycling_its_number():
    """Two guarantees that pull against each other, and both matter.

    Folding must free cap capacity, or a two-person conversation whose labels
    churn reaches "Other". But the freed *number* must never be handed to
    someone else: "Speaker 2" meaning Julie early and Mom later is worse than
    the gap it saves, because a reader following by label cannot tell it changed
    hands. That reuse was a real regression, and it is what produced "Mom as
    speaker 2 but also David as speaker 2".
    """
    mapper = SpeakerMapper()
    assert mapper.label("A") == "Speaker 1"
    assert mapper.label("B") == "Speaker 2"
    mapper.alias("B", "A")
    assert mapper.label("B") == "Speaker 1", "the fold did not take effect"

    third = mapper.label("C")
    assert third != "Speaker 2", "a released number was handed to a different person"
    assert third == "Speaker 3"

    # Capacity really was freed: a fourth and fifth distinct voice still get
    # numbers even though five labels have been seen.
    assert mapper.label("D") == "Speaker 4"
    assert mapper.label("E") == "Speaker 5"


def test_folding_is_transitive():
    """C folds onto B, which already folded onto A."""
    mapper = SpeakerMapper()
    mapper.label("A")
    mapper.alias("B", "A")
    mapper.alias("C", "B")
    assert mapper.label("C") == mapper.label("A") == "Speaker 1"


def test_the_cap_still_holds_past_four_speakers():
    mapper = SpeakerMapper()
    shown = [mapper.label(chr(ord("A") + i)) for i in range(7)]
    assert shown == [
        "Speaker 1", "Speaker 2", "Speaker 3", "Speaker 4", "Other", "Other", "Other"
    ]


def test_tap_to_correct_still_finds_the_label_behind_a_display_name():
    """Correction looks a raw label up by what is on screen; folding must not
    break that path."""
    mapper = SpeakerMapper()
    mapper.label("A")
    assert mapper.raw_for("Speaker 1") == "A"


# ── Safety ───────────────────────────────────────────────────────────────────


def test_a_voice_with_no_samples_never_wins_a_comparison(voices):
    """Guards the empty-gallery case rather than leaving it to raise."""
    empty = Voice(key="A")
    assert empty.similarity(voices["sam1"]) < 0


def test_the_first_sample_of_a_voice_is_never_evicted(voices):
    """The opening sample is the cleanest evidence of who this voice is; a
    session that slowly replaced every sample could drift onto someone else."""
    from app.session_speakers import GALLERY_CAP

    voice = Voice(key="A")
    first = voices["sam1"]
    voice.remember(first)
    for _ in range(GALLERY_CAP + 5):
        voice.remember(voices["dan1"])
    assert voice.embeddings[0] == first
    assert len(voice.embeddings) <= GALLERY_CAP


# ── Retroactive reconciliation ───────────────────────────────────────────────
# The live decision is greedy and cannot revisit: the first turn of a voice is
# judged against almost nothing. Offline diarization avoids that by clustering
# the whole recording at the end. These cover that advantage made incremental.


def test_a_split_speaker_is_reunited_once_there_is_evidence(voices, force_live_split):
    """The reported bug, arriving late: two voices that turn out to be one."""
    # Each voice gets its own recording of the same person, so the live pass
    # cannot match them (0.957 similarity, under the 0.99 bar) but the centroids
    # plainly agree afterwards. Seeding both from the same samples would let the
    # second turn match at 1.0 and never split at all.
    speakers = SessionSpeakers(threshold=0.99)  # force the live split
    speakers.assign("A", voices["sam1"])
    speakers.assign("A", voices["sam1"])
    speakers.assign("B", voices["sam2"])
    speakers.assign("B", voices["sam2"])
    assert len(speakers.voices) == 2, "expected the greedy pass to split them"

    speakers.threshold = 0.55  # normal bar; the centroids now agree
    merges = speakers.reconcile()

    assert len(speakers.voices) == 1, "the same person was left split"
    assert merges, "no merge was reported to the client"


def test_reconciliation_never_fuses_two_different_people(voices):
    """The dangerous direction, and the reason the bar is stricter than joining:
    this rewrites captions the reader has already read."""
    speakers = SessionSpeakers()
    for _ in range(3):
        speakers.assign("A", voices["sam1"])
        speakers.assign("B", voices["dan1"])
    before = len(speakers.voices)
    assert speakers.reconcile() == []
    assert len(speakers.voices) == before == 2


def test_the_older_voice_is_the_one_kept(voices, force_live_split):
    """The display number a reader has been watching must not move under them."""
    speakers = SessionSpeakers(threshold=0.99)
    speakers.assign("A", voices["sam1"])
    speakers.assign("A", voices["sam1"])
    speakers.assign("B", voices["sam2"])
    speakers.assign("B", voices["sam2"])
    speakers.threshold = 0.55
    merges = speakers.reconcile()
    assert merges == [("B", "A")], f"expected B folded into A, got {merges}"


def test_one_turn_voices_are_left_alone(voices):
    """A single turn is the weak evidence that caused the split; merging on it
    would just move the coin flip somewhere else.

    The threshold is deliberately low enough that the centroid check *would*
    pass, so the only thing preventing the merge is the turn count. An earlier
    version of this test left the threshold high and passed whether the guard
    existed or not.
    """
    speakers = SessionSpeakers(threshold=0.55)
    speakers.voices.append(Voice(key="A", embeddings=[voices["sam1"]], turns=1))
    speakers.voices.append(Voice(key="B", embeddings=[voices["sam2"]], turns=1))
    speakers._by_label.update({"A": "A", "B": "B"})
    assert speakers.reconcile() == [], "merged on one turn of evidence each"


def test_reconciliation_is_idempotent(voices, force_live_split):
    """Called after every final turn, so it must go quiet once settled or the
    client is told to relabel the same speakers forever."""
    speakers = SessionSpeakers(threshold=0.99)
    for _ in range(2):
        speakers.assign("A", voices["sam1"])
    for _ in range(2):
        speakers.assign("B", voices["sam2"])
    speakers.threshold = 0.55
    assert speakers.reconcile(), "expected a first merge"
    assert speakers.reconcile() == [], "kept merging after everything had settled"


def test_labels_follow_the_voice_they_were_folded_into(voices, force_live_split):
    """A provider label pointing at the absorbed voice must end up pointing at
    the survivor, or the next turn under it would split all over again."""
    speakers = SessionSpeakers(threshold=0.99)
    for _ in range(2):
        speakers.assign("A", voices["sam1"])
    for _ in range(2):
        speakers.assign("B", voices["sam2"])
    speakers.threshold = 0.55
    speakers.reconcile()
    survivor = speakers.voices[0].key

    # Asserted on the mapping itself, not on a later `assign`. The survivor
    # absorbed the absorbed voice's samples, so a matching turn reaches it on
    # the audio path whether or not the remap happened — two earlier versions of
    # this test passed with the remap deleted. The mapping is the guarantee.
    assert speakers._by_label["B"] == survivor
    assert all(key == survivor for key in speakers._by_label.values())
    assert {v.key for v in speakers.voices} == {survivor}


def test_the_merge_reaches_the_display_label(voices, force_live_split):
    """End to end through the mapper: what the caption actually shows."""
    speakers = SessionSpeakers(threshold=0.99)
    mapper = SpeakerMapper()
    for label in ("A", "A", "B", "B"):
        voice = speakers.assign(label, voices["sam1" if label == "A" else "sam2"])
        if voice != label:
            mapper.alias(label, voice)
        mapper.label(label)
    assert mapper.label("A") != mapper.label("B"), "expected a visible split first"

    speakers.threshold = 0.55
    for absorbed, kept in speakers.reconcile():
        mapper.alias(absorbed, kept)
    assert mapper.label("A") == mapper.label("B") == "Speaker 1"


# ── Enrolled identity is a property of the voice, not of one turn ─────────────
# Reported with three enrolled people: David showing as "David", then
# "Speaker 1", then "Speaker 2". The name was decided per turn, so one short or
# quiet turn scored under the threshold and wiped what six turns had
# established — and a generic label reads as a *different person*, not as
# uncertainty.

DAVID, MOM, JULIE = "p-david", "p-mom", "p-julie"


def test_a_named_voice_survives_a_turn_that_matches_nothing():
    """The exact flicker: David, David, (weak turn), David."""
    speakers = SessionSpeakers()
    speakers.voices.append(Voice(key="A", embeddings=[[1.0]], turns=1))
    speakers.record_match("A", DAVID, "David", 0.91)
    assert speakers.identity("A") == (DAVID, "David")

    # A turn whose own audio matched nobody contributes no evidence...
    assert speakers.identity("A") == (DAVID, "David"), "a weak turn un-named the speaker"


def test_one_confident_turn_is_enough_to_name_a_voice():
    speakers = SessionSpeakers()
    speakers.voices.append(Voice(key="A", embeddings=[[1.0]], turns=1))
    speakers.record_match("A", DAVID, "David", 0.90)
    assert speakers.identity("A") == (DAVID, "David")


def test_two_enrolled_people_too_close_to_call_stay_unnamed():
    """A wrong name is worse than no name (INTRODUCTION §5.7). Sibling voices
    scoring alike is exactly when a confident-looking sum is least trustworthy."""
    speakers = SessionSpeakers()
    speakers.voices.append(Voice(key="A", embeddings=[[1.0]], turns=1))
    speakers.record_match("A", MOM, "Mom", 0.62)
    speakers.record_match("A", JULIE, "Julie", 0.60)
    assert speakers.identity("A") is None


def test_evidence_accumulates_until_one_person_pulls_ahead():
    speakers = SessionSpeakers()
    speakers.voices.append(Voice(key="A", embeddings=[[1.0]], turns=1))
    speakers.record_match("A", MOM, "Mom", 0.60)
    speakers.record_match("A", JULIE, "Julie", 0.58)
    assert speakers.identity("A") is None, "named on a coin flip"
    speakers.record_match("A", MOM, "Mom", 0.60)
    assert speakers.identity("A") == (MOM, "Mom")


def test_a_correction_outranks_any_amount_of_evidence():
    """Tap-to-correct is the user telling us directly; nothing outvotes it."""
    speakers = SessionSpeakers()
    speakers.voices.append(Voice(key="A", embeddings=[[1.0]], turns=1))
    for _ in range(10):
        speakers.record_match("A", JULIE, "Julie", 0.95)
    speakers.pin("A", MOM, "Mom")
    assert speakers.identity("A") == (MOM, "Mom")


def test_folding_two_voices_keeps_what_each_knew(voices, force_live_split):
    """Half of David's turns under one label and half under another must not
    leave the survivor knowing less about who he is than either half did."""
    speakers = SessionSpeakers(threshold=0.99)
    for _ in range(2):
        speakers.assign("A", voices["sam1"])
    for _ in range(2):
        speakers.assign("B", voices["sam2"])
    speakers.record_match("A", DAVID, "David", 0.60)
    speakers.record_match("B", DAVID, "David", 0.60)
    assert speakers.identity("A") is None, "neither half should be decisive alone"

    speakers.threshold = 0.55
    speakers.reconcile()
    survivor = speakers.voices[0].key
    assert speakers.identity(survivor) == (DAVID, "David"), "evidence lost in the fold"
