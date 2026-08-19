"""How good is speaker identification, measured rather than asserted.

Runs constructed sessions with exact ground truth through the **production
decision path** — `SessionSpeakers.assign` → `reconcile` → `SpeakerMapper` plus
`SpeakerMatcher` for enrolled voices — and reports the metrics in
`speaker_metrics.py`.

Two modes:

    python scripts/eval_speaker_id.py                     # mock embedder, fast
    SPEAKER_ID_SERVICE=real python scripts/eval_speaker_id.py   # real ECAPA

Only the second produces numbers worth recording. The first exists to check the
harness itself runs, cheaply, without downloading a model.

**What is simulated and what is real.** The audio, the embeddings, the
clustering, the reconciliation, the naming and the display mapping are all real.
What is simulated is the *provider's diarization*: each scenario says which
diarization label the provider emitted for each turn, because that is the input
whose misbehaviour this whole subsystem exists to survive. A scenario where the
provider is always right would measure nothing — real streaming diarization
splits one voice across labels routinely, and that is the reported bug.
"""

import argparse
import json
import os
import random
import struct
import sys
import wave
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from build_speaker_corpus import CorpusError, build  # noqa: E402
from speaker_metrics import Turn, summarise  # noqa: E402

from app.session_speakers import SessionSpeakers  # noqa: E402
from app.speaker_labels import SpeakerMapper  # noqa: E402
from services.speaker_id import get_speaker_embedder  # noqa: E402
from services.speaker_id.matcher import Profile, SpeakerMatcher  # noqa: E402

RESULTS = Path(__file__).parent / "eval_results"


@dataclass
class Utterance:
    """One turn: who really spoke, and what the provider called them."""

    speaker: str
    provider_label: str
    #: Truncate the clip to this many seconds. Short turns are where ECAPA
    #: degrades — measured, a 1.0 s window scores 0.633 for the right person
    #: against a 0.55 threshold, and 0.6 s scores 0.478 and fails outright — so
    #: a suite made only of full sentences passes everything and measures
    #: nothing.
    seconds: float | None = None


def _clip(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes())


def _add_noise(pcm: bytes, level: float, rng: random.Random) -> bytes:
    """Mix in white noise at `level` x the clip's own RMS.

    Clean fixtures leave real ECAPA a very wide gap — about 0.09 between people
    and 0.9 within one — and a decision that wide is never close enough for a
    tie-break to matter. A single microphone in a room is not that clean, and
    the ambiguous band is exactly where the reported flicker lives, so a suite
    with no noise in it cannot see anything that acts on ambiguity.
    """
    if level <= 0:
        return pcm
    samples = list(struct.unpack(f"<{len(pcm) // 2}h", pcm[: len(pcm) // 2 * 2]))
    rms = (sum(s * s for s in samples) / max(1, len(samples))) ** 0.5
    amplitude = rms * level
    noisy = [
        max(-32768, min(32767, int(s + rng.gauss(0, amplitude)))) for s in samples
    ]
    return struct.pack(f"<{len(noisy)}h", *noisy)


def scenarios(speakers: list[str]) -> dict[str, list[Utterance]]:
    """The sessions to score.

    Provider labels model how streaming diarization actually misbehaves:
    `churn` issues a fresh label for the same person (the reported bug), and
    `shared` reuses one label across two people (the dangerous direction).
    """
    a, b, c, d, e = (speakers + speakers)[:5]
    return {
        # One person, and the provider keeps renaming them. Any split is wrong.
        "solo": [Utterance(a, f"P{i // 2}") for i in range(10)],
        # The common case, provider behaving.
        "pair": [Utterance(a if i % 2 == 0 else b, "P0" if i % 2 == 0 else "P1")
                 for i in range(10)],
        # Two people, provider churns labels for both.
        "pair-churn": [Utterance(a if i % 2 == 0 else b, f"P{i}") for i in range(10)],
        # Two people sharing one provider label: the merge risk.
        "pair-shared": [Utterance(a if i % 2 == 0 else b, "P0") for i in range(10)],
        # The user's actual setup.
        "trio": [Utterance([a, b, c][i % 3], f"P{i % 3}") for i in range(12)],
        "trio-churn": [Utterance([a, b, c][i % 3], f"P{i}") for i in range(12)],
        # Stated upper bound, and the four-speaker cap.
        "five": [Utterance([a, b, c, d, e][i % 5], f"P{i % 5}") for i in range(15)],
        # One speaker dominates: evidence imbalance.
        "dominant": [Utterance(a if i % 5 else b, f"P{0 if i % 5 else 1}")
                     for i in range(15)],
        # The hard case: back-and-forth in one- and two-second turns, which is
        # what real conversation is made of and where the embedder is weakest.
        "pair-short": [
            Utterance(a if i % 2 == 0 else b, "P0" if i % 2 == 0 else "P1", seconds=1.0)
            for i in range(10)
        ],
        "trio-short": [
            Utterance([a, b, c][i % 3], f"P{i % 3}", seconds=1.5) for i in range(12)
        ],
        # Short turns *and* a churning provider: both weaknesses at once.
        "trio-short-churn": [
            Utterance([a, b, c][i % 3], f"P{i}", seconds=1.0) for i in range(12)
        ],
        # Real conversation comes in runs, not strict alternation: somebody
        # holds the floor for a few turns, then hands over. Every scenario above
        # alternates on every turn, which is the one shape where "who spoke
        # last" carries no information at all — so a suite made only of those
        # cannot see a transition penalty work or fail.
        "trio-runs-short": [
            Utterance([a, a, b, b, b, c, a, a, c, c, b, a][i], f"P{i}", seconds=1.0)
            for i in range(12)
        ],
        # A third voice arrives late.
        "late-joiner": [Utterance([a, b][i % 2] if i < 8 else c, f"P{i % 2 if i < 8 else 2}")
                        for i in range(14)],
    }


def run_session(
    utterances: list[Utterance],
    clips: dict[str, list[Path]],
    matcher: SpeakerMatcher,
    enrolled: dict[str, str],
    noise: float = 0.0,
) -> list[Turn]:
    """Drive one session through the production decision path."""
    embedder = get_speaker_embedder()
    rng = random.Random(1234)  # fixed, so a run is comparable to the last one
    speakers = SessionSpeakers()
    mapper = SpeakerMapper()
    seen: dict[str, int] = {}
    turns: list[Turn] = []
    assigned: list[str] = []

    for utterance in utterances:
        # Rotate through that speaker's clips so consecutive turns are not the
        # identical waveform — otherwise every comparison scores 1.0 and the
        # evaluation measures nothing.
        index = seen.get(utterance.speaker, 0)
        seen[utterance.speaker] = index + 1
        pool = clips[utterance.speaker]
        pcm = _clip(pool[index % len(pool)])
        if utterance.seconds is not None:
            # Take from the middle: turn-initial audio is where diarization
            # most often bleeds in the previous speaker, and a leading breath
            # is not a fair sample of anyone's voice.
            want = int(utterance.seconds * 16000) * 2
            if len(pcm) > want:
                start = (len(pcm) - want) // 2
                pcm = pcm[start - start % 2 : start - start % 2 + want]

        pcm = _add_noise(pcm, noise, rng)
        embedding = embedder.embed(pcm, 16000)
        voice = speakers.assign(utterance.provider_label, embedding)

        match = matcher.match(embedding)
        if match is not None:
            speakers.record_match(voice, match.profile_id, match.display_name, match.similarity)
        identity = speakers.identity(voice)

        folded = speakers.folded_onto(utterance.provider_label, voice)
        if folded is not None:
            mapper.alias(utterance.provider_label, folded)
        # Retroactive re-clustering, exactly as the socket runs it.
        for absorbed, kept in speakers.reconcile():
            mapper.alias(absorbed, kept)

        assigned.append(voice)
        turns.append(
            Turn(
                speaker=utterance.speaker,
                label=mapper.label(voice),
                name=identity[1] if identity else None,
            )
        )

    # Reconciliation relabels captions already drawn, so the *final* mapping is
    # what the user ends up looking at. Re-resolve every turn through the voice
    # it was assigned to — not through the provider label, which can carry two
    # people and would collapse a correct split back into one speaker.
    return [
        Turn(t.speaker, mapper.label(voice), t.name)
        for t, voice in zip(turns, assigned, strict=True)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speakers", type=int, default=5)
    parser.add_argument("--enrol", type=int, default=3,
                        help="how many speakers have voice profiles")
    parser.add_argument("--noise", type=float, default=0.0,
                        help="white noise at this multiple of each clip's RMS")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    try:
        clips = build(args.speakers)
    except CorpusError as exc:
        print(f"corpus unavailable: {exc}", file=sys.stderr)
        return 1

    speaker_ids = list(clips)
    embedder = get_speaker_embedder()
    embedder.load()

    # Enrol the first N speakers from their first clip, as a real enrolment
    # would: the profile is built from different audio than the session uses
    # wherever a speaker has more than one clip.
    enrolled = {sid: sid.split("-")[-1].title() for sid in speaker_ids[: args.enrol]}
    profiles = [
        Profile(sid, name, [embedder.embed(_clip(clips[sid][0]), 16000)])
        for sid, name in enrolled.items()
    ]
    matcher = SpeakerMatcher(profiles)

    service = os.environ.get("SPEAKER_ID_SERVICE", "mock")
    print(f"\nembedder={service}  speakers={len(speaker_ids)}  "
          f"enrolled={len(enrolled)}  noise={args.noise}")
    if any(sid.startswith("tts-") for sid in speaker_ids):
        print("NOTE: TTS voices are a proxy for real speakers — absolute numbers")
        print("      are an upper bound; comparisons between runs are what carry.\n")

    header = (f"{'scenario':<14}{'turns':>6}{'confus':>8}{'split':>7}{'merge':>7}"
              f"{'count':>7}{'name%':>7}{'churn':>7}")
    print(header)
    print("-" * len(header))

    results = {}
    for name, utterances in scenarios(speaker_ids).items():
        turns = run_session(utterances, clips, matcher, enrolled, args.noise)
        stats = summarise(turns, enrolled)
        results[name] = stats
        accuracy = "  -  " if stats["name_accuracy"] is None else f"{stats['name_accuracy']:.2f}"
        print(
            f"{name:<14}{stats['turns']:>6}{stats['confusion_rate']:>8.3f}"
            f"{stats['split_rate']:>7.2f}{stats['merge_count']:>7}"
            f"{stats['count_error']:>7}{accuracy:>7}{stats['name_churn']:>7}"
        )

    merges = sum(r["merge_count"] for r in results.values())
    print(f"\ntotal merges across all scenarios: {merges}"
          f"{'  <-- MUST BE 0' if merges else '  (good)'}")

    if args.save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        path = RESULTS / f"{date.today().isoformat()}-{service}.json"
        path.write_text(json.dumps({"embedder": service, "scenarios": results}, indent=1))
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
