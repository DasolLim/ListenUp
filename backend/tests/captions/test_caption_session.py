"""A live caption session: what a turn of speech becomes on screen.

These drive `CaptionSession` directly instead of through a websocket, because
every decision below used to live inside the socket handler and could only be
reached by opening one. The transport is not the thing under test — *which
frame a turn produces* is.

The real path runs throughout: SessionNamer → SessionSpeakers → SpeakerMapper,
on the real human fixtures. Only the STT provider is mocked, because it is the
external tool (INTRODUCTION §6) and because the provider's diarization *labels*
are the input whose misbehaviour this subsystem exists to survive.
"""

import wave
from pathlib import Path

import pytest

from app.caption_session import CaptionSession, Frame
from app.naming import SessionNamer
from app.session_clock import SessionClock
from services.assemblyai.base import TranscriptSegment
from services.assemblyai.mock import MockTranscriptionService
from services.speaker_id import get_speaker_embedder
from services.speaker_id.matcher import Profile, SpeakerMatcher

FIXTURES = Path(__file__).parents[2] / "services" / "speaker_id" / "fixtures"


def pcm(name: str) -> bytes:
    with wave.open(str(FIXTURES / f"{name}.wav"), "rb") as w:
        return w.readframes(w.getnframes())


def seconds(raw: bytes) -> float:
    return len(raw) / 32000.0


def enrolled(name: str, fixture: str) -> Profile:
    """A profile enrolled from a real recording.

    Built with its embedding rather than filled in afterwards: `SpeakerMatcher`
    drops a profile that has none, so a profile enrolled after construction is
    silently not in the gallery at all.
    """
    return Profile("p1", name, [get_speaker_embedder().embed(pcm(fixture), 16000)])


def final(
    speaker: str, start: float, end: float, turn_id: int, text: str = "hello"
) -> TranscriptSegment:
    return TranscriptSegment(
        speaker=speaker, text=text, start=start, end=end, is_final=True, turn_id=turn_id
    )


async def session(profiles: list[Profile] | None = None, **kwargs) -> CaptionSession:
    """A started session on the mock transport, as `open()` would hand one back."""
    service = MockTranscriptionService()
    await service.start(16000, "pcm_s16le", "en")
    return CaptionSession(service, SessionNamer(SpeakerMatcher(profiles or [])), **kwargs)


def bodies(frames: list[Frame], kind: str) -> list[dict]:
    return [f.body for f in frames if f.body.get("type") == kind]


async def speak(cs: CaptionSession, name: str, speaker: str, turn_id: int) -> list[Frame]:
    """Stream one fixture recording as a whole turn under `speaker`."""
    raw = pcm(name)
    start = cs.audio_seconds
    await cs.push_audio(raw)
    return await cs.observe(final(speaker, start, start + seconds(raw), turn_id))


# ── The caption label is the voice, not the provider's label ─────────────────


@pytest.mark.anyio
async def test_two_people_under_one_provider_label_get_two_speaker_numbers():
    """The dangerous direction. Diarization putting two voices under one label
    is routine; letting the display collapse them attributes words to somebody
    who never said them, and a reader who cannot hear the original cannot catch
    it."""
    cs = await session()
    first = await speak(cs, "sam1", "A", 0)
    second = await speak(cs, "dan1", "A", 1)

    labels = [bodies(first, "segment")[0]["speaker"], bodies(second, "segment")[0]["speaker"]]
    assert labels[0] != labels[1], f"two people share the label {labels[0]}"


@pytest.mark.anyio
async def test_one_voice_under_three_labels_stays_one_speaker_number():
    """The reported bug: one person alone was Speaker 1, then 2, then 3."""
    cs = await session()
    shown = []
    for i, (name, label) in enumerate([("sam1", "A"), ("sam2", "B"), ("sam1", "C")]):
        frames = await speak(cs, name, label, i)
        shown.append(bodies(frames, "segment")[0]["speaker"])
    assert shown == ["Speaker 1"] * 3, shown


# ── What may be dropped when a client falls behind ───────────────────────────


@pytest.mark.anyio
async def test_an_interim_may_be_shed_under_backpressure_but_a_final_may_not():
    """An interim is superseded by the next one anyway; a final is the only
    record of a sentence, so losing one loses words off the transcript."""
    cs = await session()
    await cs.push_audio(pcm("sam1"))
    interim = TranscriptSegment(
        speaker="A", text="hel", start=0.0, end=1.0, is_final=False, turn_id=0
    )
    interim_frames = await cs.observe(interim)
    final_frames = await cs.observe(final("A", 0.0, 5.0, 0))

    assert bodies(interim_frames, "segment") and interim_frames[0].droppable
    assert bodies(final_frames, "segment") and not final_frames[0].droppable


# ── Naming ───────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_name_is_announced_once_per_speaker_not_once_per_turn():
    """`speakerUpdate` back-fills a speaker's earlier unnamed bubbles. Re-sending
    it on every later turn is pure noise on the wire and makes the client redo
    the same pass over the whole transcript for each sentence."""
    # Enrolled from the same voice the session will hear, so the match is
    # certain and this is about the announcement, not about the matcher.
    cs = await session([enrolled("Sam", "sam1")])

    first = await speak(cs, "sam1", "A", 0)
    second = await speak(cs, "sam2", "A", 1)

    assert [u["speakerName"] for u in bodies(first, "speakerUpdate")] == ["Sam"]
    assert bodies(first, "speakerUpdate")[0]["fillOnly"] is True
    assert bodies(second, "speakerUpdate") == [], "the name was announced twice"


@pytest.mark.anyio
async def test_a_correction_names_the_speaker_and_a_correction_to_nobody_clears_it():
    """Tap-to-correct is the one name allowed to stick, so it has to be able to
    say 'not that person' as well as 'this person'."""
    cs = await session([enrolled("Mom", "dan1")])
    await speak(cs, "sam1", "A", 0)

    named = await cs.correct("Speaker 1", "p1")
    assert bodies(named, "speakerUpdate") == [
        {"type": "speakerUpdate", "speaker": "Speaker 1", "speakerName": "Mom"}
    ]

    cleared = await cs.correct("Speaker 1", None)
    assert bodies(cleared, "speakerUpdate") == [
        {"type": "speakerUpdate", "speaker": "Speaker 1", "speakerName": None}
    ]


@pytest.mark.anyio
async def test_a_correction_for_a_label_nobody_is_using_changes_nothing():
    cs = await session()
    assert await cs.correct("Speaker 4", "p1") == []


# ── Pause ────────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_audio_sent_while_paused_never_reaches_the_provider():
    """The client stops sending on pause, so this only catches frames already in
    flight — but 'paused' has to mean nothing is transcribed, or the promise the
    button makes is not one the server keeps."""
    cs = await session()
    await cs.pause()
    accepted = await cs.push_audio(pcm("sam1"))
    assert accepted is False
    assert cs.audio_seconds == 0.0, "paused audio was still buffered for naming"


class FlushSpy(MockTranscriptionService):
    """A transport that buffers, so `flush` means something to it."""

    def __init__(self) -> None:
        super().__init__()
        self.flushes = 0

    async def flush(self) -> None:
        self.flushes += 1


@pytest.mark.anyio
async def test_pausing_closes_the_current_utterance():
    """A buffering transport would otherwise hold the half-finished window
    through the pause and complete it with whatever is said after — one caption
    spanning two moments, which a reader has no way to notice."""
    service = FlushSpy()
    cs = CaptionSession(service, SessionNamer(SpeakerMatcher([])))
    await cs.pause()
    assert service.flushes == 1


# ── What the session costs ───────────────────────────────────────────────────


class Meter:
    """Stands in for the billing Caller: the database is the external thing."""

    def __init__(self) -> None:
        self.charges: list[tuple[str, int]] = []

    async def record(self, metric: str, amount: int) -> None:
        self.charges.append((metric, amount))


class FakeTime:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.mark.anyio
async def test_a_pause_is_not_billed():
    """The socket stays open across a pause so the transcript survives. Billing
    a held-open session would make the pause button cost the same as not
    pausing."""
    clock = FakeTime()
    meter = Meter()
    cs = await session(clock=SessionClock(now=clock), who=meter)
    clock.t = 10.0
    await cs.pause()
    clock.t = 310.0  # five minutes holding the socket open
    cs.resume()
    clock.t = 320.0
    await cs.close()

    assert meter.charges == [("captions", 20)], "the pause was billed"


@pytest.mark.anyio
async def test_a_session_that_reached_ready_bills_at_least_one_second():
    """It cost a real STT connection, and `int()` truncation would round every
    session down — an error that accumulates in one direction across a month."""
    clock = FakeTime()
    meter = Meter()
    cs = await session(clock=SessionClock(now=clock), who=meter)
    clock.t = 0.4
    await cs.close()
    assert meter.charges == [("captions", 1)]


@pytest.mark.anyio
async def test_an_unauthenticated_session_is_captioned_and_billed_to_nobody():
    """Captions are the accessibility core: no account still means captions."""
    cs = await session()
    await speak(cs, "sam1", "A", 0)
    await cs.close()  # must not raise for want of a caller
