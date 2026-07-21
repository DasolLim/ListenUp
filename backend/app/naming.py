"""Per-session speaker naming: buffers diarized audio, embeds lazily, and
caches provider-label → display-name for the whole session (embed once per
speaker, not per segment)."""

import asyncio
import logging
import os
from dataclasses import dataclass, field

from app.supa import rest
from services.assemblyai.base import BYTES_PER_SECOND, TranscriptSegment
from services.speaker_id import get_speaker_embedder
from services.speaker_id.matcher import Match, Profile, SpeakerMatcher

logger = logging.getLogger("listenup.naming")

# Identify from a short window first (session adaptation makes 2s reliable),
# then keep retrying with more audio as the person talks. Only re-embed when
# meaningfully more audio is available, to bound CPU. All tunable via env.
MIN_MATCH_AUDIO_S = float(os.environ.get("SPEAKER_MIN_MATCH_S", "2.0"))
MAX_MATCH_AUDIO_S = float(os.environ.get("SPEAKER_MAX_MATCH_S", "8.0"))
RETRY_GROWTH_S = float(os.environ.get("SPEAKER_RETRY_GROWTH_S", "1.2"))
MAX_ATTEMPTS_PER_SPEAKER = int(os.environ.get("SPEAKER_MAX_ATTEMPTS", "8"))
BUFFER_CAP_S = 180.0

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
    attempts: int = 0
    last_attempt_audio_s: float = 0.0  # so we only re-embed on meaningful growth
    resolved: Match | None = None
    done: bool = False  # stop trying after success or attempt cap


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
        """Manual override (tap-to-correct)."""
        state = self._speakers.setdefault(raw_speaker, _SpeakerState())
        state.resolved = match
        state.done = True

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

    async def observe(self, segment: TranscriptSegment) -> Match | None:
        """Feed a FINAL segment; maybe embed + match. Returns the current name."""
        if not segment.is_final:
            state = self._speakers.get(segment.speaker)
            return state.resolved if state else None
        state = self._speakers.setdefault(segment.speaker, _SpeakerState())
        state.windows.append((segment.start, segment.end))

        if state.done or not self.matcher.profiles:
            return state.resolved

        pcm = self.speaker_audio(segment.speaker)
        audio_s = len(pcm) / BYTES_PER_SECOND
        if audio_s < MIN_MATCH_AUDIO_S:
            return state.resolved  # not enough voice yet — wait for more turns
        # Skip re-embedding until meaningfully more audio has accumulated.
        if state.attempts > 0 and audio_s - state.last_attempt_audio_s < RETRY_GROWTH_S:
            return state.resolved

        state.attempts += 1
        state.last_attempt_audio_s = audio_s
        self.embeds_computed += 1
        embedder = get_speaker_embedder()
        try:
            embedding = await asyncio.to_thread(embedder.embed, pcm, 16000)
        except ValueError:
            return state.resolved
        logger.info(
            "naming_attempt raw=%s audio=%.1fs attempt=%d", segment.speaker, audio_s, state.attempts
        )
        match = self.matcher.match(embedding)  # matcher logs best/runner-up/score
        if match is not None:
            state.resolved = match
            state.done = True
            # Session adaptation: remember confident matches so this person's
            # later turns (even under new diarization labels) re-match fast.
            if match.similarity >= self.matcher.threshold + SESSION_ADAPT_MARGIN:
                self._adapt(match.profile_id, embedding)
            logger.info(
                "speaker_named raw=%s name=%s similarity=%.3f attempts=%d",
                segment.speaker, match.display_name, match.similarity, state.attempts,
            )
        elif state.attempts >= MAX_ATTEMPTS_PER_SPEAKER:
            state.done = True
            logger.info("speaker_stays_generic raw=%s attempts=%d", segment.speaker, state.attempts)
        return state.resolved
