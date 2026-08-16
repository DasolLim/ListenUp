"""Who is speaking, decided from the voice rather than from the provider's label.

The problem this exists for: one person, talking alone, was being labelled
Speaker 1, then Speaker 2, then Speaker 3. Nothing was wrong with the matcher —
it was never consulted. The displayed identity was the *diarization label*,
mapped positionally to "Speaker N", and streaming diarization splits a single
voice across labels routinely (after a pause, a gain change, or simply because
one speaker gives it no contrast to anchor on). The whole voice-identity system
sat behind an enrolment check (`if not self.matcher.profiles: return`), so a
user who had never enrolled got raw labels and nothing else.

Enrolment is the wrong precondition for this. Knowing *that two turns came from
the same person* needs no enrolment at all — only the ability to compare two
voices, which the local ECAPA embedder already does on CPU for free. Enrolment
is what turns "the same person" into "Mom", and that remains a separate step.

So turns are clustered by voice within the session. The provider still decides
*when* the speaker changed — that is what diarization is genuinely good at, and
it drives turn boundaries — but the cluster decides *who*, and clusters survive
label churn by construction.

**Which error this leans away from.** Splitting one person into two labels is
the reported annoyance; merging two people into one label attributes words to
someone who never said them, which for a reader who cannot hear the original is
unfalsifiable. So a turn joins an existing voice only on a confident match and
otherwise starts a new one: the failure mode kept is the visible, correctable
one. Real ECAPA leaves a wide gap to work in — the same voice in two different
recordings scores ~0.91, two different people ~0.09 — so the threshold is not
finely balanced between them.
"""

import logging
import os
from dataclasses import dataclass, field

from services.speaker_id.base import cosine_similarity

logger = logging.getLogger("listenup.session_speakers")

# Same default as profile matching, tunable separately because it answers a
# different question: "is this the voice we heard a moment ago" rather than "is
# this the person who enrolled last week". Recordings minutes apart in one room
# are more alike than an enrolment weeks old, so if these ever diverge this one
# should be the stricter.
DEFAULT_CLUSTER_THRESHOLD = 0.55

# Embeddings kept per voice. More samples make later turns match better, since a
# voice drifts within a session (leaning closer to the mic, tiring, laughing).
GALLERY_CAP = int(os.environ.get("SESSION_VOICE_GALLERY_CAP", "12"))

# A ceiling on distinct voices tracked. The UI caps at 4 named speakers plus
# "Other", so tracking far past that buys nothing and lets a noisy room grow
# this unboundedly. Past the cap a turn joins its nearest voice rather than
# inventing another.
MAX_VOICES = int(os.environ.get("SESSION_MAX_VOICES", "8"))

# Below this, the audio is positive evidence of a *different* person, and a
# label that already has a voice is split rather than kept.
#
# There are three bands, not two, because "not confidently the same" and
# "confidently different" are different claims. Between this floor and the match
# threshold the evidence is ambiguous, and the label keeps the voice it has:
# that is where an atypical turn lives — quiet, off-mic, laughing — and churning
# on it would recreate the reported bug from the other direction. Real ECAPA
# leaves the bands well separated (same voice ~0.9, different ~0.09).
SPLIT_FLOOR = float(os.environ.get("SPEAKER_SPLIT_FLOOR", "0.45"))

# Retroactive merging is held to a stricter bar than joining, because it
# rewrites captions the reader has already read. Joining decides where the next
# line goes; this decides that a line they saw attributed to Speaker 2 was
# always Speaker 1. Being wrong here is more expensive, so it needs more
# evidence — and unlike the live decision, it can afford to wait for it.
RECONCILE_MARGIN = float(os.environ.get("SPEAKER_RECONCILE_MARGIN", "0.10"))

# Compared on centroids rather than best-pair similarity. Max-cosine merges two
# voices on a single flattering pair of samples; the centroid asks whether the
# two collections of audio are the same person on the whole, which is the
# question a retroactive rewrite is actually answering.
MIN_TURNS_TO_RECONCILE = int(os.environ.get("SPEAKER_MIN_TURNS_RECONCILE", "2"))


def _centroid(embeddings: list[list[float]]) -> list[float]:
    """Mean embedding. Cosine ignores magnitude, so the mean stands in for the
    voice as a whole without needing renormalisation."""
    width = len(embeddings[0])
    return [sum(e[i] for e in embeddings) / len(embeddings) for i in range(width)]


def cluster_threshold() -> float:
    return float(os.environ.get("SPEAKER_CLUSTER_THRESHOLD", DEFAULT_CLUSTER_THRESHOLD))


@dataclass
class Voice:
    """One distinct voice heard in this session.

    `key` is the diarization label this voice was *first* heard under. Naming it
    after the first label rather than inventing an id keeps every downstream
    lookup — display numbering, the speaker cap, tap-to-correct — on the one
    namespace it already uses.
    """

    key: str
    embeddings: list[list[float]] = field(default_factory=list)
    turns: int = 0

    def similarity(self, embedding: list[float]) -> float:
        """Best cosine across everything heard from this voice so far.

        A voice with nothing recorded loses every comparison rather than
        raising: it can exist briefly, before the first turn is judged.
        """
        if not self.embeddings:
            return -1.0
        return max(cosine_similarity(embedding, sample) for sample in self.embeddings)

    def remember(self, embedding: list[float]) -> None:
        self.embeddings.append(embedding)
        if len(self.embeddings) > GALLERY_CAP:
            # Drop the second-oldest, never the first: the opening sample is the
            # cleanest evidence of who this voice is, and a session that slowly
            # replaces every sample can drift onto a different person entirely.
            del self.embeddings[1]


class SessionSpeakers:
    """Voice-derived speaker identity for one session. No enrolment required."""

    def __init__(self, threshold: float | None = None) -> None:
        self.threshold = threshold if threshold is not None else cluster_threshold()
        self.voices: list[Voice] = []
        # Last voice each provider label resolved to. Not a freeze — a label that
        # later sounds like someone else is re-pointed — but it is what stops a
        # single ambiguous turn from splitting a speaker in two.
        self._by_label: dict[str, str] = {}

    def assign(self, provider_label: str, embedding: list[float]) -> str:
        """The voice this turn belongs to.

        **Merge-only.** A turn may join a voice the session has already heard,
        and a provider label that has been seen before keeps the voice it was
        given — but audio alone never invents a speaker the provider did not
        report. So the number of voices can only ever be *fewer* than the number
        of diarization labels, never more.

        That direction is the whole point. The reported failure is
        over-segmentation: one person arriving as Speaker 1, 2 and 3. Letting
        embeddings split as well as merge would add a second, independent way to
        produce exactly that symptom, on audio the model may simply find
        ambiguous — a bad trade for a fix aimed at it.
        """
        scored = sorted(
            ((voice.similarity(embedding), voice) for voice in self.voices),
            key=lambda pair: pair[0],
            reverse=True,
        )
        best_score, best = scored[0] if scored else (0.0, None)

        # The voice says this is someone already heard. Trust it over the label:
        # this is the merge that collapses churned labels back into one person.
        if best is not None and best_score >= self.threshold:
            if self._by_label.get(provider_label) != best.key:
                logger.info(
                    "voice_merged label=%s -> %s score=%.3f", provider_label, best.key, best_score
                )
            self._remember(best, provider_label, embedding)
            return best.key

        # Ambiguous, and this label already has a voice: keep it. A quiet or
        # atypical turn from a known speaker must not become a new one. But if
        # the audio is positively *unlike* that voice, the label really is
        # carrying a second person — which streaming diarization does — and
        # keeping it would attribute their words to someone else.
        known = self._by_label.get(provider_label)
        if known is not None:
            voice = next(v for v in self.voices if v.key == known)
            if voice.similarity(embedding) > SPLIT_FLOOR:
                self._remember(voice, provider_label, embedding)
                return voice.key
            logger.info(
                "voice_split label=%s from=%s score=%.3f floor=%.2f",
                provider_label, voice.key, voice.similarity(embedding), SPLIT_FLOOR,
            )

        if len(self.voices) >= MAX_VOICES and best is not None:
            self._remember(best, provider_label, embedding)
            return best.key

        # Keyed on the label it was first heard under, so a split gets a key
        # nobody is using: the label itself is taken by the voice it is leaving.
        key = (
            provider_label
            if provider_label not in self._by_label
            else f"{provider_label}#{len(self.voices) + 1}"
        )
        voice = Voice(key=key)
        self.voices.append(voice)
        self._remember(voice, provider_label, embedding)
        logger.info(
            "voice_new key=%s label=%s best_existing=%.3f threshold=%.2f voices=%d",
            voice.key, provider_label, best_score, self.threshold, len(self.voices),
        )
        return voice.key

    def _remember(self, voice: Voice, provider_label: str, embedding: list[float]) -> None:
        voice.remember(embedding)
        voice.turns += 1
        self._by_label[provider_label] = voice.key

    def reconcile(self) -> list[tuple[str, str]]:
        """Merge voices that later evidence shows were one person all along.

        The live decision is greedy and online: it commits with whatever it has
        heard so far, and it can never revisit. That is the structural reason a
        single speaker fragments — the first turn of what is really one voice is
        judged against almost nothing, and once a second voice exists the two
        drift on separately.

        Offline diarization avoids this by clustering the whole recording at the
        end, with every segment in hand. This is that idea made incremental:
        after each turn, ask whether any two voices have accumulated enough
        evidence to show they are the same person, and if so fold them and tell
        the client to relabel what it already drew.

        Returns `(absorbed, kept)` key pairs, oldest voice kept so the display
        number a reader has been watching does not move.
        """
        merges: list[tuple[str, str]] = []
        changed = True
        while changed:
            changed = False
            for i, keeper in enumerate(self.voices):
                for other in self.voices[i + 1 :]:
                    if not self._same_person(keeper, other):
                        continue
                    for sample in other.embeddings:
                        keeper.remember(sample)
                    keeper.turns += other.turns
                    for label, key in list(self._by_label.items()):
                        if key == other.key:
                            self._by_label[label] = keeper.key
                    self.voices.remove(other)
                    merges.append((other.key, keeper.key))
                    logger.info("voice_reconciled absorbed=%s into=%s", other.key, keeper.key)
                    changed = True
                    break
                if changed:
                    break
        return merges

    def _same_person(self, a: Voice, b: Voice) -> bool:
        """Are these two collections of audio one person, on the whole?

        Both need enough turns to have a stable centroid: one-turn voices are
        exactly the weak evidence that produced the split, and merging on them
        would just move the coin flip somewhere else.
        """
        if a.turns < MIN_TURNS_TO_RECONCILE or b.turns < MIN_TURNS_TO_RECONCILE:
            return False
        if not a.embeddings or not b.embeddings:
            return False
        return cosine_similarity(_centroid(a.embeddings), _centroid(b.embeddings)) >= (
            self.threshold + RECONCILE_MARGIN
        )
