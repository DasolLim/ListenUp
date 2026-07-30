"""SessionNamer must name each turn by the voice in it.

Two properties are asserted here, and they pull in opposite directions:

* the same voice under new diarization labels stays one person, and
* one diarization label covering different people names each of them correctly.

The second is the regression: identity used to be decided once per label and
frozen, so when speakers alternated, whoever spoke first under a label kept the
name — the reported "it calls me the previous person for a while" bug.
"""

import asyncio
import wave
from pathlib import Path

import numpy as np

from app.naming import SessionNamer
from services.assemblyai.base import TranscriptSegment
from services.speaker_id import get_speaker_embedder
from services.speaker_id.matcher import Profile, SpeakerMatcher

FIXTURES = Path(__file__).parent.parent / "services" / "speaker_id" / "fixtures"
SR = 16000

# Three synthetic voices, distinct in formant structure (the thing that makes
# people sound different). Generated rather than committed as fixtures: three
# real multi-speaker recordings would be ~2 MB of binaries to test logic that
# only needs "reliably different voices", and these are deterministic.
_VOICES = {
    "alice": (210.0, [(700, 90, 1.0), (1900, 140, 0.8), (3100, 200, 0.5)]),
    "bob": (110.0, [(450, 80, 1.0), (1100, 120, 0.9), (2400, 180, 0.4)]),
    "cara": (170.0, [(600, 85, 1.0), (2500, 160, 0.85), (3600, 220, 0.6)]),
}


def say(name: str, seconds: float, take: int = 0) -> bytes:
    """Deterministic PCM for one speaker: a harmonic source shaped by fixed
    formants, so takes of one voice match and different voices don't."""
    f0, formants = _VOICES[name]
    rng = np.random.default_rng(abs(hash((name, take))) % 10_000)
    n = int(SR * seconds)
    t = np.arange(n) / SR
    signal = np.zeros(n)
    for harmonic in range(1, 25):
        signal += (1.0 / harmonic) * np.sin(
            2 * np.pi * f0 * harmonic * t + rng.uniform(0, 0.2)
        )
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    envelope = np.full_like(freqs, 0.05)
    for centre, width, gain in formants:
        envelope += gain * np.exp(-((freqs - centre) ** 2) / (2 * width**2))
    out = np.fft.irfft(spectrum * envelope, n)
    out += rng.normal(0, 0.002, n)  # a little mic noise
    out = out / (np.abs(out).max() or 1.0) * 0.7
    return (out * 32767).astype(np.int16).tobytes()


def enrolled_matcher() -> SpeakerMatcher:
    embedder = get_speaker_embedder()
    return SpeakerMatcher(
        [
            Profile(name, name.capitalize(), [embedder.embed(say(name, 20.0, take=99))])
            for name in _VOICES
        ],
        threshold=0.55,
        margin=0.05,
    )


def conversation(namer: SessionNamer, turns: list[tuple[str, float]]) -> list[str]:
    """Speak `turns` into `namer` back to back; return the label each got."""
    audio = bytearray()
    windows = []
    clock = 0.0
    for index, (speaker, seconds) in enumerate(turns):
        audio.extend(say(speaker, seconds, take=index))
        windows.append((clock, clock + seconds))
        clock += seconds
    namer.add_audio(bytes(audio))
    return windows  # type: ignore[return-value]


def pcm(name: str) -> bytes:
    with wave.open(str(FIXTURES / f"{name}.wav"), "rb") as w:
        return w.readframes(w.getnframes())


def final(raw: str, start: float, end: float, turn_id: int = 0) -> TranscriptSegment:
    return TranscriptSegment(
        speaker=raw, text="hello there", start=start, end=end, is_final=True, turn_id=turn_id
    )


def interim(raw: str, start: float, end: float, turn_id: int = 0) -> TranscriptSegment:
    return TranscriptSegment(
        speaker=raw, text="hello", start=start, end=end, is_final=False, turn_id=turn_id
    )


# ── Real-time naming (while the person is still speaking) ─────────────────────

def test_speaker_is_named_during_the_turn_not_only_when_it_ends() -> None:
    """Identifying only on the final segment means the caption carries the old
    name for the whole turn and then flips — visibly naming the wrong person
    first. A turn must be identified from the voice as it is being spoken."""
    namer = SessionNamer(enrolled_matcher())
    conversation(namer, [("bob", 3.0)])

    async def run() -> str | None:
        # 1.5s into the turn, before any final arrives.
        match = await namer.observe(interim("A", 0.0, 1.5, turn_id=1))
        return match.display_name if match else None

    assert asyncio.run(run()) == "Bob"


def test_a_new_speaker_after_a_pause_is_not_shown_as_the_previous_one() -> None:
    """The reported symptom: the caption shows the previous speaker while the
    new one talks. After a pause the name must be dropped until verified —
    unnamed is honest, the previous person's name is not."""
    namer = SessionNamer(enrolled_matcher())
    # Alice, one second of silence, then Bob.
    audio = bytearray(say("alice", 3.0, take=0))
    audio.extend(b"\x00" * (SR * 2))  # 1.0s silence (16-bit mono)
    audio.extend(say("bob", 3.0, take=1))
    namer.add_audio(bytes(audio))

    async def run() -> tuple[str | None, str | None]:
        await namer.observe(final("A", 0.0, 3.0, turn_id=1))
        # Bob's turn opens; too little voice yet to identify anyone.
        early = await namer.observe(interim("A", 4.0, 4.4, turn_id=2))
        # ...and once there is enough, it is Bob, never Alice.
        later = await namer.observe(interim("A", 4.0, 5.6, turn_id=2))
        return (
            early.display_name if early else None,
            later.display_name if later else None,
        )

    assert asyncio.run(run()) == (None, "Bob")


def test_interim_matching_is_bounded_per_turn() -> None:
    """Interim segments arrive several times a second; embedding every one
    would burn CPU for no benefit."""
    from app.naming import MAX_INTERIM_EMBEDS_PER_TURN

    namer = SessionNamer(enrolled_matcher())
    conversation(namer, [("cara", 8.0)])

    async def run() -> int:
        before = namer.embeds_computed
        for tenth in range(10, 80):  # 70 interim frames across one turn
            await namer.observe(interim("A", 0.0, tenth / 10, turn_id=1))
        return namer.embeds_computed - before

    assert asyncio.run(run()) <= MAX_INTERIM_EMBEDS_PER_TURN


# ── The reported bug ──────────────────────────────────────────────────────────

def test_alternating_speakers_are_each_named_on_their_own_turn() -> None:
    """Three enrolled people talking in turns, all under ONE diarization label.

    This is the reported failure in its harshest form: with identity frozen per
    label, every turn after the first was named for whoever spoke first.
    """
    namer = SessionNamer(enrolled_matcher())
    turns = [("alice", 3.0), ("bob", 3.0), ("cara", 3.0), ("bob", 3.0), ("alice", 3.0)]
    windows = conversation(namer, turns)

    async def run() -> list[str | None]:
        names = []
        for (_speaker, _), (start, end) in zip(turns, windows, strict=True):
            match = await namer.observe(final("A", start, end))
            names.append(match.display_name if match else None)
        return names

    assert asyncio.run(run()) == ["Alice", "Bob", "Cara", "Bob", "Alice"]


def test_speaker_change_is_caught_on_the_next_turn_not_after_several() -> None:
    """Diarization lag: a new speaker's turn lands on the previous speaker's
    label. The name must follow the voice immediately, not lag behind it."""
    namer = SessionNamer(enrolled_matcher())
    turns = [("alice", 3.0), ("bob", 3.0), ("alice", 3.0), ("cara", 3.0)]
    windows = conversation(namer, turns)
    labels = ["A", "A", "B", "B"]  # labels lag one turn behind the real speaker

    async def run() -> list[str | None]:
        names = []
        for label, (start, end) in zip(labels, windows, strict=True):
            match = await namer.observe(final(label, start, end))
            names.append(match.display_name if match else None)
        return names

    assert asyncio.run(run()) == ["Alice", "Bob", "Alice", "Cara"]


def test_one_voice_under_many_labels_is_still_one_person() -> None:
    """The property the old design got right must survive the fix."""
    namer = SessionNamer(enrolled_matcher())
    turns = [("bob", 3.0), ("bob", 3.0), ("bob", 3.0)]
    windows = conversation(namer, turns)

    async def run() -> list[str | None]:
        names = []
        for label, (start, end) in zip(["A", "B", "C"], windows, strict=True):
            match = await namer.observe(final(label, start, end))
            names.append(match.display_name if match else None)
        return names

    assert asyncio.run(run()) == ["Bob", "Bob", "Bob"]


def test_a_manual_correction_is_not_overruled_by_the_matcher() -> None:
    """Tap-to-correct is the user telling us who this is; re-identifying each
    turn must not undo it."""
    from services.speaker_id.matcher import Match

    namer = SessionNamer(enrolled_matcher())
    turns = [("alice", 3.0), ("alice", 3.0)]
    windows = conversation(namer, turns)

    async def run() -> str | None:
        await namer.observe(final("A", *windows[0]))
        namer.set_name("A", Match("cara", "Cara", 1.0))
        match = await namer.observe(final("A", *windows[1]))
        return match.display_name if match else None

    assert asyncio.run(run()) == "Cara"


def test_a_turn_too_short_to_judge_does_not_invent_a_name() -> None:
    """Below the minimum there isn't enough voice to be sure. The label's last
    identity carries provisionally — but nothing new is asserted from a
    fragment, and a following full turn re-decides it."""
    namer = SessionNamer(enrolled_matcher())
    turns = [("alice", 3.0), ("bob", 0.4), ("bob", 3.0)]
    windows = conversation(namer, turns)

    async def run() -> list[str | None]:
        names = []
        for start, end in windows:
            match = await namer.observe(final("A", start, end))
            names.append(match.display_name if match else None)
        return names

    # The 0.4s fragment keeps Alice (provisional, honest); the full turn corrects.
    assert asyncio.run(run()) == ["Alice", "Alice", "Bob"]


def test_short_turns_are_named_rather_than_left_generic() -> None:
    """Back-and-forth conversation is mostly short turns. Refusing to judge
    anything under the confident window left real speech permanently unnamed."""
    namer = SessionNamer(enrolled_matcher())
    turns = [("alice", 1.4), ("bob", 1.4), ("cara", 1.4), ("alice", 1.4)]
    windows = conversation(namer, turns)

    async def run() -> list[str | None]:
        names = []
        for (_speaker, _), (start, end) in zip(turns, windows, strict=True):
            match = await namer.observe(final("A", start, end))
            names.append(match.display_name if match else None)
        return names

    assert asyncio.run(run()) == ["Alice", "Bob", "Cara", "Alice"]


def test_identified_speech_is_not_reused_as_evidence_for_the_next_turn() -> None:
    """A short turn may borrow adjacent audio only if nobody has been credited
    with it. Without this, continuous speech (where every turn abuts the last)
    let a fragment swallow the previous speaker's identified words and inherit
    their name.
    """
    namer = SessionNamer(enrolled_matcher())
    # A long Alice turn, then a short Bob turn butted directly against it.
    turns = [("alice", 3.0), ("bob", 1.2)]
    windows = conversation(namer, turns)

    async def run() -> list[str | None]:
        names = []
        for start, end in windows:
            match = await namer.observe(final("A", start, end))
            names.append(match.display_name if match else None)
        return names

    assert asyncio.run(run()) == ["Alice", "Bob"]


def test_turn_audio_does_not_stitch_across_a_pause() -> None:
    """The window used for identification must stay inside one utterance.

    Reaching back across a gap is how two speakers ended up blended into a
    single embedding that matched the wrong person.
    """
    from app.naming import _SpeakerState

    namer = SessionNamer(enrolled_matcher())
    conversation(namer, [("alice", 3.0), ("bob", 3.0)])

    # A short, unowned window separated from the latest turn by a long silence.
    # Unowned means rule 3 permits it, so only the gap rule can exclude it.
    across_a_pause = _SpeakerState()
    across_a_pause.windows = [(0.0, 1.0), (10.0, 11.0)]
    across_a_pause.window_owners = [None, None]
    assert len(namer.turn_audio(across_a_pause)) / 32000 <= 1.1, "stitched across the pause"

    # The same windows butted together are one utterance, so they may combine.
    contiguous = _SpeakerState()
    contiguous.windows = [(0.0, 1.0), (1.0, 2.0)]
    contiguous.window_owners = [None, None]
    assert len(namer.turn_audio(contiguous)) / 32000 > 1.5, "contiguous audio was not used"


def test_identity_survives_label_churn() -> None:
    embedder = get_speaker_embedder()  # mock in CI
    voice = pcm("sam1")  # ~5s of one speaker
    enrolled = embedder.embed(voice)
    matcher = SpeakerMatcher([Profile("p1", "Alex", [enrolled])], threshold=0.55, margin=0.05)
    namer = SessionNamer(matcher)
    namer.add_audio(voice)  # same voice fills the session buffer

    async def run() -> list[str | None]:
        results = []
        # the SAME voice appears under three different diarization labels
        for raw, start, end in [("A", 0.0, 2.5), ("B", 2.5, 5.0), ("C", 0.0, 2.5)]:
            match = await namer.observe(final(raw, start, end))
            results.append(match.display_name if match else None)
        return results

    assert asyncio.run(run()) == ["Alex", "Alex", "Alex"]


def test_session_gallery_is_capped() -> None:
    embedder = get_speaker_embedder()
    enrolled = embedder.embed(pcm("sam1"))
    profile = Profile("p1", "Alex", [enrolled])
    namer = SessionNamer(SpeakerMatcher([profile], threshold=0.55, margin=0.05))
    for _ in range(20):
        namer._adapt("p1", embedder.embed(pcm("sam2")))
    # 1 enrolled + at most SESSION_GALLERY_CAP runtime embeddings
    from app.naming import SESSION_GALLERY_CAP

    assert len(profile.embeddings) == 1 + SESSION_GALLERY_CAP
