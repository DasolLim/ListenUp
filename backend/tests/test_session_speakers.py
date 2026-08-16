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


def test_the_number_of_tracked_voices_is_bounded(voices):
    speakers = SessionSpeakers(threshold=0.99)
    for i in range(MAX_VOICES + 5):
        speakers.assign(f"label-{i}", voices["sam1"] if i % 2 else voices["dan1"])
    assert len(speakers.voices) <= MAX_VOICES


# ── The display mapper ───────────────────────────────────────────────────────


def test_a_folded_label_releases_its_speaker_slot():
    """A label is usually shown once as an interim before its audio is judged.
    Leaving that reservation behind spends the four-speaker cap on people who
    turned out not to exist."""
    mapper = SpeakerMapper()
    assert mapper.label("A") == "Speaker 1"
    assert mapper.label("B") == "Speaker 2"
    mapper.alias("B", "A")
    assert mapper.label("B") == "Speaker 1"
    # Speaker 2 is free again, so the next real person takes it.
    assert mapper.label("C") == "Speaker 2"


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
