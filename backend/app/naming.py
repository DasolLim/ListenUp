"""Per-session speaker naming: buffers diarized audio and identifies **each
turn** from the voice in that turn.

Identity is a property of the voice, not of the diarization label. An earlier
version resolved a label once and froze it (`done=True`), which made the label
the identity: when diarization reused a label for a different person — or
attributed the start of a new speaker's turn to the previous speaker's label,
which streaming diarization does routinely — every later turn under that label
kept the first person's name. Speakers switching back and forth were therefore
named as whoever spoke first under that label, until diarization happened to
issue a fresh label. Each final turn is now matched on its own audio, so a
switch is caught on the very next turn.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field

from app.supa import rest
from services.assemblyai.base import BYTES_PER_SECOND, TranscriptSegment
from services.speaker_id import get_speaker_embedder
from services.speaker_id.matcher import Match, Profile, SpeakerMatcher

logger = logging.getLogger("listenup.naming")

# Audio needed to name a turn outright (session adaptation makes 2s reliable).
MIN_MATCH_AUDIO_S = float(os.environ.get("SPEAKER_MIN_MATCH_S", "2.0"))
MAX_MATCH_AUDIO_S = float(os.environ.get("SPEAKER_MAX_MATCH_S", "8.0"))
BUFFER_CAP_S = 180.0

# Back-and-forth conversation is full of one- and two-second turns. Refusing to
# judge them at all leaves real speech permanently unnamed, so they are matched
# on their own audio but held to a higher bar (below) — the honest way to use
# weak evidence is to demand more of it, not to stitch other speech onto it.
SHORT_TURN_MIN_S = float(os.environ.get("SPEAKER_SHORT_TURN_MIN_S", "1.0"))
SHORT_TURN_MARGIN = float(os.environ.get("SPEAKER_SHORT_TURN_MARGIN", "0.10"))

# When a turn is too short to identify alone, it may be extended backwards with
# earlier audio from the same label — but only across gaps this small. A short
# gap means one continuous utterance that diarization split; a longer one is
# where a different person can have taken over, and stitching across it is what
# produces a blended embedding that matches nobody (or worse, the wrong person).
CONTIGUOUS_GAP_S = float(os.environ.get("SPEAKER_CONTIGUOUS_GAP_S", "0.75"))

# Session adaptation (online enrollment): once a voice is confidently matched,
# remember how it sounds THIS session (same mic/room) so later turns — even
# short ones under a churning diarization label — re-match fast. Only adapt on
# confident matches, and cap the per-profile gallery to bound cost and drift.
SESSION_ADAPT_MARGIN = float(os.environ.get("SPEAKER_ADAPT_MARGIN", "0.08"))
SESSION_GALLERY_CAP = int(os.environ.get("SPEAKER_GALLERY_CAP", "6"))


async def load_profiles(token: str) -> list[Profile]:
    """Fetch the user's profiles + embeddings once at session start (RLS applies)."""
    response = await rest(
        "GET",
        "speaker_profiles",
        token,
        params={"select": "id,display_name,speaker_embeddings(embedding)"},
    )
    if response.status_code != 200:
        logger.warning("profiles_load_failed status=%s", response.status_code)
        return []
    profiles = []
    for row in response.json():
        embeddings = [
            [float(x) for x in item["embedding"].strip("[]").split(",")]
            for item in row.get("speaker_embeddings", [])
            if item.get("embedding")
        ]
        profiles.append(Profile(row["id"], row["display_name"], embeddings))
    return profiles


@dataclass
class _SpeakerState:
    windows: list[tuple[float, float]] = field(default_factory=list)
    # Who each window was attributed to, positionally aligned with `windows`.
    # `None` means "never judged" — only that audio may be borrowed to help
    # identify a later short turn, so speech already credited to a person can
    # never become evidence for someone else.
    window_owners: list[str | None] = field(default_factory=list)
    attempts: int = 0
    # Last identity seen under this label. Provisional only: it names turns too
    # short to judge, and is replaced the moment a long-enough turn disagrees.
    resolved: Match | None = None
    # A human said who this is (tap-to-correct). That beats the matcher and is
    # the one case where a label's name is allowed to stick.
    overridden: bool = False


class SessionNamer:
    """One per enhanced WS session."""

    def __init__(self, matcher: SpeakerMatcher) -> None:
        self.matcher = matcher
        self._audio = bytearray()
        self._dropped_s = 0.0  # seconds trimmed off the buffer's front
        self._speakers: dict[str, _SpeakerState] = {}
        # How many embeddings each profile was enrolled with, so session-adapted
        # runtime embeddings can be capped without discarding enrolled ones.
        self._enrolled_count = {p.profile_id: len(p.embeddings) for p in matcher.profiles}
        self.embeds_computed = 0

    def _adapt(self, profile_id: str, embedding: list[float]) -> None:
        """Add a confidently-matched runtime embedding to the profile's gallery
        (in memory only), capped, so future turns match this session's audio."""
        for profile in self.matcher.profiles:
            if profile.profile_id != profile_id:
                continue
            profile.embeddings.append(embedding)
            enrolled = self._enrolled_count.get(profile_id, 0)
            if len(profile.embeddings) > enrolled + SESSION_GALLERY_CAP:
                del profile.embeddings[enrolled]  # drop oldest session embedding
            return

    def add_audio(self, chunk: bytes) -> None:
        self._audio.extend(chunk)
        overflow = len(self._audio) - int(BUFFER_CAP_S * BYTES_PER_SECOND)
        if overflow > 0:
            del self._audio[:overflow]
            self._dropped_s += overflow / BYTES_PER_SECOND

    def _slice(self, start: float, end: float) -> bytes:
        lo = max(0, int((start - self._dropped_s) * BYTES_PER_SECOND))
        hi = max(0, int((end - self._dropped_s) * BYTES_PER_SECOND))
        # keep sample alignment (2 bytes)
        return bytes(self._audio[lo - lo % 2 : hi - hi % 2])

    def name_for(self, raw_speaker: str) -> Match | None:
        state = self._speakers.get(raw_speaker)
        return state.resolved if state else None

    def set_name(self, raw_speaker: str, match: Match | None) -> None:
        """Manual override (tap-to-correct). Sticks for the rest of the session."""
        state = self._speakers.setdefault(raw_speaker, _SpeakerState())
        state.resolved = match
        state.overridden = True

    def speaker_audio(self, raw_speaker: str, max_seconds: float = MAX_MATCH_AUDIO_S) -> bytes:
        state = self._speakers.get(raw_speaker)
        if state is None:
            return b""
        parts: list[bytes] = []
        total = 0.0
        for start, end in reversed(state.windows):
            piece = self._slice(start, end)
            if not piece:
                continue
            parts.append(piece)
            total += len(piece) / BYTES_PER_SECOND
            if total >= max_seconds:
                break
        return b"".join(reversed(parts))

    def turn_audio(self, state: _SpeakerState, target_seconds: float = MIN_MATCH_AUDIO_S) -> bytes:
        """Audio for the turn that just ended — that turn alone whenever possible.

        Three rules, each one a bug that was caught in QA:

        1. **Never reach back when the turn can stand alone.** Grabbing extra
           audio "to be safe" is what blended two speakers into one embedding.
        2. **Only cross near-zero gaps.** A sub-`CONTIGUOUS_GAP_S` join is one
           utterance that diarization split; a longer one is where somebody else
           can have taken over.
        3. **Only borrow audio nobody has been credited with.** In continuous
           speech consecutive turns abut, so rule 2 alone still let a short turn
           swallow the previous speaker's identified words. Audio already
           attributed to a person is off limits as evidence for anyone else.
        """
        if not state.windows:
            return b""
        start, end = state.windows[-1]
        parts = [self._slice(start, end)]
        total = len(parts[0]) / BYTES_PER_SECOND
        earliest = start
        # `window_owners` trails `windows` by one here: the current turn has not
        # been judged yet, so pair each earlier window with its own owner.
        earlier = list(zip(state.windows[:-1], state.window_owners[:-1], strict=False))
        for (window_start, window_end), owner in reversed(earlier):
            if total >= target_seconds or earliest - window_end > CONTIGUOUS_GAP_S:
                break
            if owner is not None:
                break  # already somebody's words
            piece = self._slice(window_start, window_end)
            if not piece:
                break
            parts.append(piece)
            total += len(piece) / BYTES_PER_SECOND
            earliest = window_start
        return b"".join(reversed(parts))

    async def observe(self, segment: TranscriptSegment) -> Match | None:
        """Feed a FINAL segment; identify the speaker of *this turn*.

        Every long-enough turn is re-identified from its own audio, so a speaker
        change is caught on the next turn instead of inheriting whoever the
        label resolved to first.
        """
        if not segment.is_final:
            state = self._speakers.get(segment.speaker)
            return state.resolved if state else None
        state = self._speakers.setdefault(segment.speaker, _SpeakerState())
        state.windows.append((segment.start, segment.end))
        state.window_owners.append(None)

        # A human already said who this is; don't second-guess them.
        if state.overridden or not self.matcher.profiles:
            return state.resolved

        pcm = self.turn_audio(state)
        audio_s = len(pcm) / BYTES_PER_SECOND
        if audio_s < SHORT_TURN_MIN_S:
            # Too little voice to judge honestly. Carry the label's last identity
            # as a provisional name rather than guessing from a fragment; the
            # next judgeable turn re-decides it, and this window stays unowned so
            # it can help identify that turn.
            return state.resolved

        state.attempts += 1
        self.embeds_computed += 1
        embedder = get_speaker_embedder()
        try:
            embedding = await asyncio.to_thread(embedder.embed, pcm, 16000)
        except ValueError:
            return state.resolved
        match = self.matcher.match(embedding)  # matcher logs best/runner-up/score
        # Weak evidence needs a stronger result: a turn under the confident
        # window is only named when the match clears an extra margin, so a
        # one-second fragment can't rename someone on a coin-flip score.
        if (
            match is not None
            and audio_s < MIN_MATCH_AUDIO_S
            and match.similarity < self.matcher.threshold + SHORT_TURN_MARGIN
        ):
            logger.info(
                "speaker_short_turn_unsure raw=%s audio=%.1fs best=%s similarity=%.3f",
                segment.speaker, audio_s, match.display_name, match.similarity,
            )
            match = None

        previous = state.resolved
        # The match decides this turn outright, including back to None: keeping a
        # stale name because it was confident once is the bug this replaces.
        state.resolved = match
        state.window_owners[-1] = match.profile_id if match else None

        if match is not None:
            # Session adaptation: remember confident matches so this person's
            # later turns (even under new diarization labels) re-match fast.
            if match.similarity >= self.matcher.threshold + SESSION_ADAPT_MARGIN:
                self._adapt(match.profile_id, embedding)
            if previous is None or previous.profile_id != match.profile_id:
                logger.info(
                    "speaker_named raw=%s name=%s similarity=%.3f audio=%.1fs was=%s",
                    segment.speaker, match.display_name, match.similarity, audio_s,
                    previous.display_name if previous else "-",
                )
        elif previous is not None:
            logger.info(
                "speaker_unnamed raw=%s was=%s audio=%.1fs (below threshold — staying generic)",
                segment.speaker, previous.display_name, audio_s,
            )
        return state.resolved
