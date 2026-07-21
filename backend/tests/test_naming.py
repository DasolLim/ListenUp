"""SessionNamer keeps a person's identity stable across diarization label churn:
the same voice appearing under new speaker labels must still resolve to the
enrolled profile (this is what makes enhanced captions consistent)."""

import asyncio
import wave
from pathlib import Path

from app.naming import SessionNamer
from services.assemblyai.base import TranscriptSegment
from services.speaker_id import get_speaker_embedder
from services.speaker_id.matcher import Profile, SpeakerMatcher

FIXTURES = Path(__file__).parent.parent / "services" / "speaker_id" / "fixtures"


def pcm(name: str) -> bytes:
    with wave.open(str(FIXTURES / f"{name}.wav"), "rb") as w:
        return w.readframes(w.getnframes())


def final(raw: str, start: float, end: float) -> TranscriptSegment:
    return TranscriptSegment(speaker=raw, text="hello there", start=start, end=end, is_final=True)


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
