"""Build the audio corpus the speaker-identity evaluation runs on.

Two sources, in order of trust:

1. **Real human recordings** already in `services/speaker_id/fixtures` — `sam1`,
   `sam2` (one person, two takes) and `dan1` (a different person). These are the
   only genuinely trustworthy voices here.
2. **macOS `say` voices**, to reach five speakers. A proxy, and stated as one
   wherever numbers are reported: ECAPA may separate synthetic voices more
   cleanly than real ones, so absolute figures from a TTS-heavy scenario are an
   upper bound. Comparisons between runs still carry, which is what the harness
   is for.

**Two guards, and the second one is the one that nearly got away.**

*Silence.* `say -v ?` lists voices that are not actually installed; asking for
one can write about 0.02 s of silence and exit 0. That has already produced a
fabricated accuracy figure in this repo — a run that was 95% silence scored
22.6% and was read as a transcription result.

*Distinctness.* A voice that is not installed may instead be rendered in the
**system default voice**, silently. Measured here: `say -v Samantha` and
`say -v Alex` produced byte-identical audio, and both matched an existing
"human" fixture at 0.87 cosine. A corpus like that has two real speakers wearing
five names, so every merge metric is inflated and the system is blamed for the
harness. Passing the silence check proves a clip contains speech; it proves
nothing about *whose* speech. So each accepted voice must also be acoustically
distinct from every voice already accepted.
"""

import argparse
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent.parent / "services" / "speaker_id" / "fixtures"
CORPUS = FIXTURES / "corpus"  # gitignored; regenerate rather than commit

SAMPLE_RATE = 16000

# Human-sounding system voices only. The installed list also contains novelty
# voices (Bells, Boing, Bubbles, Cellos, Wobble, Jester) which are not a proxy
# for anything and would make the separation look far easier than it is.
TTS_VOICES = ["Samantha", "Alex", "Daniel", "Karen", "Moira", "Tessa", "Fred", "Victoria"]

# Sentences long enough to embed, varied enough not to score phonetic overlap as
# speaker similarity.
LINES = [
    "Are you coming over for dinner on Sunday evening with the rest of them?",
    "I told her the meeting was moved to Thursday but she had already left.",
    "We should probably leave a bit earlier if we want to beat the traffic.",
    "The whole thing turned out better than anyone was expecting, honestly.",
    "Can you remind me what time the appointment is supposed to start today?",
    "It rained the entire weekend so we stayed inside and watched films.",
    "She said the new place near the station is worth trying at least once.",
    "Nobody mentioned that the tickets had to be collected before six o'clock.",
]

# A clip must be at least this fraction of the duration we asked for, and carry
# real energy. Both, not either: a truncated clip can still be loud, and a
# full-length clip can still be silence.
MIN_DURATION_RATIO = 0.5
MIN_RMS = 200.0  # int16; measured room noise sits well under this

# Two accepted speakers may not be closer than this. Real ECAPA puts different
# people around 0.09 and the same person around 0.91, so anything above this is
# the same voice under two names rather than two similar people.
MAX_SPEAKER_SIMILARITY = 0.45


class CorpusError(RuntimeError):
    """A clip could not be produced or did not contain speech."""


def read_wav(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes()), handle.getframerate()


def write_wav(path: Path, pcm: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def rms(pcm: bytes) -> float:
    if len(pcm) < 2:
        return 0.0
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm[: len(pcm) // 2 * 2])
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def assert_is_speech(path: Path, expected_seconds: float) -> None:
    """Refuse a clip that cannot prove it contains speech.

    Raises rather than warns. A silent clip that reaches the evaluation makes
    every number downstream meaningless while looking perfectly plausible.
    """
    pcm, rate = read_wav(path)
    seconds = len(pcm) / 2 / rate
    if seconds < expected_seconds * MIN_DURATION_RATIO:
        raise CorpusError(
            f"{path.name}: {seconds:.2f}s of audio, expected about "
            f"{expected_seconds:.2f}s — the voice is probably not installed"
        )
    level = rms(pcm)
    if level < MIN_RMS:
        raise CorpusError(
            f"{path.name}: RMS {level:.1f} is below the speech floor {MIN_RMS} — "
            "this clip is silence"
        )


def say(voice: str, text: str, destination: Path) -> None:
    """Render one line with a system voice, at the sample rate the pipeline uses."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Straight to WAV at the pipeline's own rate. Writing LEI16 into an
        # .aiff container fails outright, which is worth remembering: the error
        # looks like "this voice is missing" when it is really the container.
        subprocess.run(
            ["say", "-v", voice, "-o", str(destination),
             "--data-format=LEI16@16000", text],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise CorpusError(f"could not render {voice}: {exc}") from exc


def available_voices(reference: list[list[float]] | None = None) -> list[str]:
    """System voices that render speech **and** sound like nobody already taken.

    Being listed by `say -v ?` means nothing: an uninstalled voice may render as
    silence, or worse, in the system default voice — which passes every
    loudness and duration check while quietly being a duplicate of another
    speaker. Both failures are rejected here, loudly.
    """
    from services.speaker_id import get_speaker_embedder
    from services.speaker_id.base import cosine_similarity

    embedder = get_speaker_embedder()
    accepted: list[list[float]] = list(reference or [])
    usable: list[str] = []
    probe = CORPUS / "_probe"

    for voice in TTS_VOICES:
        target = probe / f"{voice}.wav"
        try:
            say(voice, LINES[0], target)
            assert_is_speech(target, expected_seconds=2.0)
            pcm, rate = read_wav(target)
            embedding = embedder.embed(pcm, rate)
            twin = next(
                (cosine_similarity(embedding, other) for other in accepted
                 if cosine_similarity(embedding, other) >= MAX_SPEAKER_SIMILARITY),
                None,
            )
            if twin is not None:
                raise CorpusError(
                    f"sounds like a voice already accepted (cosine {twin:.3f}) — "
                    "probably not installed and rendered in the default voice"
                )
            accepted.append(embedding)
            usable.append(voice)
        except CorpusError as exc:
            print(f"  rejected {voice}: {exc}", file=sys.stderr)
        finally:
            target.unlink(missing_ok=True)

    if probe.exists() and not any(probe.iterdir()):
        probe.rmdir()
    return usable


def build(speakers_wanted: int) -> dict[str, list[Path]]:
    """Clips per speaker id. Real humans first, TTS to make up the number."""
    CORPUS.mkdir(parents=True, exist_ok=True)
    corpus: dict[str, list[Path]] = {
        # Two takes of one person: the only real same-speaker variation available.
        "human-sam": [FIXTURES / "sam1.wav", FIXTURES / "sam2.wav"],
        "human-dan": [FIXTURES / "dan1.wav"],
    }
    for path in (p for paths in corpus.values() for p in paths):
        if not path.is_file():
            raise CorpusError(f"missing human fixture {path}")

    if speakers_wanted <= len(corpus):
        return dict(list(corpus.items())[:speakers_wanted])

    print("rendering TTS voices (a proxy for real speakers — see module docstring)")
    from services.speaker_id import get_speaker_embedder

    embedder = get_speaker_embedder()
    # The human fixtures are themselves generated audio, so a system voice can
    # collide with them too — measured at 0.87. They seed the distinctness check.
    reference = []
    for paths in corpus.values():
        pcm, rate = read_wav(paths[0])
        reference.append(embedder.embed(pcm, rate))
    voices = available_voices(reference)
    needed = speakers_wanted - len(corpus)
    if len(voices) < needed:
        raise CorpusError(
            f"only {len(voices)} usable system voices, need {needed} more speakers"
        )

    for voice in voices[:needed]:
        clips = []
        for index, line in enumerate(LINES):
            target = CORPUS / f"tts-{voice.lower()}-{index}.wav"
            if not target.exists():
                say(voice, line, target)
                assert_is_speech(target, expected_seconds=2.5)
            clips.append(target)
        corpus[f"tts-{voice.lower()}"] = clips
    return corpus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speakers", type=int, default=5)
    args = parser.parse_args()
    try:
        corpus = build(args.speakers)
    except CorpusError as exc:
        print(f"corpus build failed: {exc}", file=sys.stderr)
        return 1
    print(f"\n{len(corpus)} speakers:")
    for speaker, clips in corpus.items():
        print(f"  {speaker:<20} {len(clips)} clip(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
