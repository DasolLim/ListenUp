"""One live captioning session — everything except the wire.

The websocket route used to be a 320-line function that did all of this inline:
resolve who is asking, check their allowance, load their voice profiles, start
the right transport for the language, decide what a diarized turn becomes on
screen, fold two labels into one person, back-fill names, bill the session. The
transport and the product decisions were braided together, so none of the
decisions could be reached without opening a socket, and the route knew every
detail of all of them.

They are separated here. `CaptionSession` answers the questions the *product*
answers — which speaker is this, what does the client need to be told, what does
this session cost — and hands back `Frame`s. The route below it does one thing:
move frames over a websocket. Everything a session needs to know is reachable
through five methods:

    session = await CaptionSession.open(config)   # or SessionRefused
    async for segment in session.segments():
        for frame in await session.observe(segment): ...
    await session.push_audio(pcm)   /  pause() / resume() / correct(...)
    await session.close()           # meters the session

See the module docstring of `app/routes/transcribe.py` for the client protocol.
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.naming import SessionNamer, load_profiles
from app.session_clock import SessionClock
from app.speaker_labels import SpeakerMapper
from app.timing import record
from services.assemblyai.base import (
    BATCH_LANGUAGES,
    TranscriptionService,
    TranscriptSegment,
    assert_spoken_language,
)
from services.assemblyai.factory import get_transcription_service
from services.speaker_id.matcher import Profile, SpeakerMatcher

logger = logging.getLogger("listenup.caption_session")


class Meterable(Protocol):
    """The slice of the billing `Caller` a session actually uses.

    Stated as a protocol rather than imported, because `app.routes.billing`
    imports far more than a session needs and importing it here would make the
    session depend on the HTTP layer it exists to be independent of.
    """

    async def record(self, metric: str, amount: int) -> None: ...


@dataclass(frozen=True)
class Frame:
    """One message bound for the client.

    `droppable` is the frame saying what may happen to it when a slow client
    falls behind, rather than the queue guessing. The queue used to sniff for
    the substring `"isFinal": true` in the encoded JSON, which is a decision
    about captions written in the vocabulary of a serialiser — and it would have
    started silently shedding finals the day the payload gained a field or the
    separators changed.
    """

    body: dict[str, Any]
    droppable: bool = False

    def encode(self) -> str:
        return json.dumps(self.body)


class SessionRefused(Exception):
    """The session may not start, and the client is owed a reason.

    Carries what to send and how to close, so every refusal in `open()` reaches
    the socket the same way instead of each one re-implementing send-then-close.
    """

    def __init__(self, frame: Frame, code: int, reason: str = "") -> None:
        super().__init__(reason or frame.body.get("message", "refused"))
        self.frame = frame
        self.code = code
        self.reason = reason


@dataclass
class SessionCost:
    """What the session spent, for the one line written when it ends."""

    chunks: int = 0
    billed_seconds: int = 0
    paused_seconds: float = 0.0


async def _resolve_caller(token: str, client: str) -> Any:
    """Who this session belongs to, or None if we could not find out.

    Failure degrades to an unmetered, unnamed session rather than refusing to
    caption. Captions are the accessibility core; a billing lookup that times
    out must never be the reason someone can't follow a conversation.
    """
    try:
        from app.routes.billing import caller_for_token

        return await caller_for_token(token)
    except Exception:
        logger.warning("transcribe_auth_failed client=%s", client)
        return None


def _allowance_frames(who: Any) -> list[Frame]:
    """The allowance is checked *before* the session starts and never again.

    That is the whole design: a cap that fires mid-sentence can fire in a
    medical appointment, so it blocks the next start instead and the session
    already running always finishes.

    Raises `SessionRefused` when there is nothing left; returns the one-off 80%
    notice otherwise, so the user can decide how to spend what remains rather
    than discovering the cap when it arrives.
    """
    spent = who.allowance("captions")
    if spent.blocked:
        raise SessionRefused(
            Frame(
                {
                    "type": "error",
                    "reason": "limit_reached",
                    "metric": "captions",
                    "plan": who.plan.tier,
                    "resetsAt": who.usage.period_end,
                    "upgradeTo": "basic" if who.plan.tier == "free" else "pro",
                    "message": "You've used all your caption hours for this billing period.",
                }
            ),
            code=1008,
            reason="caption allowance reached",
        )
    if spent.warning:
        return [
            Frame(
                {
                    "type": "usage",
                    "metric": "captions",
                    "used": spent.used,
                    "limit": spent.limit,
                    "remaining": spent.remaining,
                    "resetsAt": who.usage.period_end,
                }
            )
        ]
    return []


class CaptionSession:
    """What a live caption session decides. See the module docstring."""

    def __init__(
        self,
        service: TranscriptionService,
        namer: SessionNamer,
        *,
        language: str = "en",
        who: Meterable | None = None,
        token: str | None = None,
        clock: SessionClock | None = None,
        client: str = "?",
        notices: list[Frame] | None = None,
    ) -> None:
        self.service = service
        self.namer = namer
        self.language = language
        # Korean has no streaming model, so it runs in buffered (batch) mode —
        # the UI tells the user captions arrive a few seconds behind rather than
        # looking broken.
        self.mode = "batch" if language in BATCH_LANGUAGES else "streaming"
        self.client = client
        self._who = who
        self._token = token
        # The clock starts when captioning actually begins: a session refused
        # for a bad format or an exhausted allowance never gets one, so it costs
        # the user nothing. It stops on pause, so holding the socket open
        # between two halves of a conversation is free.
        self._clock = clock if clock is not None else SessionClock()
        self._mapper = SpeakerMapper()
        # Names already sent to the client, so a back-fill is announced once.
        self._announced: dict[str, str] = {}
        self._notices = list(notices or [])
        self.cost = SessionCost()
        self.audio_seconds = 0.0

    # ── Opening ──────────────────────────────────────────────────────────────

    @classmethod
    async def open(cls, config: Mapping[str, Any], *, client: str = "?") -> "CaptionSession":
        """Assemble a session from the client's opening message.

        Raises `SessionRefused` for anything the client can be told about: an
        unsupported language, an audio format we can't read, an exhausted
        allowance.
        """
        from services.assemblyai import AudioFormatError
        from services.assemblyai.base import UnsupportedLanguageError

        fixture = config.get("fixture")
        if fixture and os.environ.get("TRANSCRIPTION_SERVICE", "mock").lower() == "mock":
            os.environ["MOCK_FIXTURE"] = str(fixture)

        language = str(config.get("language") or "en").lower()
        try:
            assert_spoken_language(language)
        except UnsupportedLanguageError as exc:
            raise SessionRefused(
                Frame({"type": "error", "message": str(exc)}), code=1003
            ) from exc

        # A token is resolved whenever one is sent, not only in enhanced mode:
        # caption *minutes* are metered on every tier, so the session needs to
        # know who it belongs to even when no naming is requested.
        token = str(config["token"]) if config.get("token") else None
        who = await _resolve_caller(token, client) if token else None
        notices = _allowance_frames(who) if who is not None else []

        service = get_transcription_service(language)
        namer = SessionNamer(SpeakerMatcher(await _load_gallery(token, client)))
        session = cls(
            service,
            namer,
            language=language,
            who=who,
            token=token,
            client=client,
            notices=notices,
        )

        try:
            await service.start(
                sample_rate=int(config.get("sampleRate", 0)),
                encoding=str(config.get("encoding", "")),
                language=language,
            )
        except AudioFormatError as exc:
            logger.warning("transcribe_bad_format client=%s error=%s", client, exc)
            raise SessionRefused(
                Frame({"type": "error", "message": str(exc)}), code=1003
            ) from exc

        logger.info(
            "transcribe_start client=%s service=%s language=%s mode=%s",
            client, type(service).__name__, language, session.mode,
        )
        return session

    @property
    def opening_frames(self) -> list[Frame]:
        """Everything the client is owed before the first caption.

        Any allowance notice comes *before* `ready`: the 80% warning exists so
        someone can decide how to spend what is left, and a warning that arrives
        after "listening" has already been announced is a warning about a
        session they have started.
        """
        return [
            *self._notices,
            Frame({"type": "ready", "language": self.language, "mode": self.mode}),
        ]

    def segments(self) -> AsyncIterator[TranscriptSegment]:
        return self.service.segments()

    # ── Audio in ─────────────────────────────────────────────────────────────

    async def push_audio(self, pcm: bytes) -> bool:
        """Feed a chunk. False means it was dropped because we are paused.

        The client stops sending on pause, so this normally only catches frames
        already in flight — but "paused" has to mean nothing is transcribed, or
        the promise the button makes is not one the server keeps.
        """
        if self._clock.paused:
            return False
        self.cost.chunks += 1
        self.audio_seconds += len(pcm) / 32000.0
        self.namer.add_audio(pcm)
        await self.service.send_audio(pcm)
        return True

    # ── Turns out ────────────────────────────────────────────────────────────

    async def observe(self, segment: TranscriptSegment) -> list[Frame]:
        """Everything the client is owed for one diarized turn.

        The caption itself, plus whatever the turn changed: a merge that
        relabels captions already on screen, and a name to back-fill onto this
        speaker's earlier unnamed bubbles.
        """
        # The provider decides *when* the speaker changed, which is what
        # diarization is good at. It does not decide *who*: it splits one voice
        # across labels routinely, which is how a single person came out as
        # Speaker 1, 2 and 3. The voice key does decide, so the label survives
        # that churn — and falls back to the provider's label only when the turn
        # was too short to judge from audio at all.
        voice, match = await self.namer.identify(segment)
        name = match.display_name if match else None

        # Folding is still needed in the other direction: a label shown once as
        # an interim, before there was audio to judge, holds a speaker slot, and
        # when its turns turn out to belong to a voice first heard elsewhere
        # that slot has to be released or the cap is spent on people who do not
        # exist.
        if voice is not None:
            folded = self.namer.speakers.folded_onto(segment.speaker, voice)
            if folded is not None:
                self._mapper.alias(segment.speaker, folded)
        label = self._mapper.label(voice or segment.speaker)

        frames = [
            Frame(
                {
                    "type": "segment",
                    "speaker": label,
                    "speakerName": name,
                    "text": segment.text,
                    "start": round(segment.start, 3),
                    "end": round(segment.end, 3),
                    "isFinal": segment.is_final,
                    "turnId": segment.turn_id,
                },
                # An interim is superseded by the next one anyway; a final is
                # the only record of that sentence.
                droppable=not segment.is_final,
            )
        ]

        if segment.is_final:
            self._record_lag(segment, named=name is not None)
            frames.extend(self._reconciliation_frames())
        frames.extend(self._naming_frames(label, name))
        return frames

    def _record_lag(self, segment: TranscriptSegment, *, named: bool) -> None:
        """Caption lag as the *user* experiences it.

        Measured here rather than inside each transport because all three
        converge on this one path — instrumenting them separately would be three
        chances to miss one, and the streaming path would have silently reported
        nothing.

        `clock.elapsed()` rather than raw wall time: `segment.end` is a position
        in the audio timeline, which does not advance while paused, so
        subtracting one from the other without excluding the pause would report
        every caption after it as late by the length of the pause.
        """
        lag_ms = (self._clock.elapsed() - segment.end) * 1000
        record(
            "stt_window",
            max(0.0, lag_ms),
            language=self.language,
            mode=self.mode,
            # Separates this from the batch API round trip, which shares the
            # span name; mixing them would corrupt the aggregate.
            stage="caption",
            named=named,
        )

    def _reconciliation_frames(self) -> list[Frame]:
        """Offline diarization clusters the whole recording at the end, which is
        why its attribution beats anything decided live. This is that advantage
        taken incrementally: once two voices have enough audio to show they were
        one person, fold them and relabel the captions already drawn rather than
        leaving the split on screen."""
        frames = []
        for absorbed, kept in self.namer.speakers.reconcile():
            was = self._mapper.label(absorbed)
            self._mapper.alias(absorbed, kept)
            now = self._mapper.label(kept)
            if was != now:
                frames.append(Frame({"type": "speakerMerge", "from": was, "to": now}))
                logger.info("speaker_merge_emitted from=%s to=%s", was, now)
        return frames

    def _naming_frames(self, label: str, name: str | None) -> list[Frame]:
        """Name resolved: fill in this speaker's earlier bubbles that were still
        unnamed. `fillOnly` matters now that a label can carry different people
        over a session — without it, naming the current turn would rewrite the
        previous speaker's history under the same label."""
        if name is None or self._announced.get(label) == name:
            return []
        self._announced[label] = name
        return [
            Frame(
                {
                    "type": "speakerUpdate",
                    "speaker": label,
                    "speakerName": name,
                    "fillOnly": True,
                }
            )
        ]

    # ── Corrections ──────────────────────────────────────────────────────────

    async def correct(self, label: str, profile_id: str | None) -> list[Frame]:
        """Tap-to-correct: remap the session label now, and append this
        speaker's buffered audio as a correction embedding so the profile
        improves for next time."""
        from services.speaker_id.matcher import Match

        raw = self._mapper.raw_for(label)
        if raw is None:
            return []

        if profile_id is None:
            self.namer.set_name(raw, None)
            logger.info("correction_applied label=%s -> unknown", label)
            return [
                Frame({"type": "speakerUpdate", "speaker": label, "speakerName": None})
            ]

        profile = next(
            (p for p in self.namer.matcher.profiles if p.profile_id == profile_id), None
        )
        if profile is None:
            return []
        self.namer.set_name(raw, Match(profile.profile_id, profile.display_name, 1.0))
        await self._learn_from_correction(raw, profile, label)
        return [
            Frame(
                {
                    "type": "speakerUpdate",
                    "speaker": label,
                    "speakerName": profile.display_name,
                }
            )
        ]

    async def _learn_from_correction(self, raw: str, profile: Profile, label: str) -> None:
        """Append what this speaker has said so far to their enrolled gallery.

        Best-effort by design: the correction has already been applied on screen,
        so a database that will not take the embedding costs the user a better
        match next session, never the name they just fixed.
        """
        from app.supa import rest
        from services.speaker_id import get_speaker_embedder

        pcm = self.namer.speaker_audio(raw)
        if not self._token or len(pcm) < 16000:  # ≥0.5 s of audio to learn from
            return
        try:
            embedding = await asyncio.to_thread(get_speaker_embedder().embed, pcm, 16000)
            response = await rest(
                "POST",
                "speaker_embeddings",
                self._token,
                json={
                    "profile_id": profile.profile_id,
                    "embedding": str(embedding),
                    "source": "correction",
                },
            )
            if response.status_code == 201:
                profile.embeddings.append(embedding)  # better matching immediately
                logger.info(
                    "correction_applied label=%s -> %s embedding_appended=1",
                    label, profile.display_name,
                )
        except ValueError:
            logger.info(
                "correction_applied label=%s -> %s (audio too short to learn)",
                label, profile.display_name,
            )

    # ── Pause, and the end ───────────────────────────────────────────────────

    async def pause(self) -> Frame:
        self._clock.pause()
        # Close the current utterance before the audio stops. On a buffering
        # transport the half-finished window would otherwise wait through the
        # pause and be completed by whatever is said after it — one caption
        # spanning two moments. A no-op on the streaming transports.
        await self.service.flush()
        logger.info("transcribe_pause client=%s chunks=%d", self.client, self.cost.chunks)
        return Frame({"type": "paused"})

    def resume(self) -> Frame:
        self._clock.resume()
        logger.info(
            "transcribe_resume client=%s paused_s=%.1f",
            self.client, self._clock.paused_seconds(),
        )
        return Frame({"type": "resumed"})

    async def end_input(self) -> None:
        """Graceful stop: no more audio is coming, flush what is left."""
        await self.service.stop()

    async def close(self) -> None:
        """Stop the transport and bill the session.

        Metered on close rather than on a timer: the number we owe is the length
        of the session, and recording it once means a dropped connection cannot
        leave a partially-counted session behind.

        Rounded, not truncated: `int()` always rounds down, so every session
        would under-count by up to a second and the error would accumulate in
        one direction across a month. A session that reached `ready` at all cost
        a real STT connection, so it bills at least one second rather than being
        free — and `elapsed()` excludes time the user spent paused, because the
        socket stays open across a pause so the transcript survives and billing
        a held-open session would make the pause button cost the same as not
        pausing.
        """
        await self.service.stop()
        self.cost.billed_seconds = max(1, round(self._clock.elapsed()))
        self.cost.paused_seconds = self._clock.paused_seconds()
        if self._who is not None:
            await self._who.record("captions", self.cost.billed_seconds)
        logger.info(
            "transcribe_end client=%s chunks=%d billed_s=%d paused_s=%.1f",
            self.client, self.cost.chunks, self.cost.billed_seconds, self.cost.paused_seconds,
        )


async def _load_gallery(token: str | None, client: str) -> list[Profile]:
    """This user's enrolled voices, or an empty gallery.

    Speaker naming runs for every session, signed in or not, and is not behind a
    flag. It used to require `enhanced: true` from the client, which made naming
    a product choice — it never was one: nobody knowingly picks the version that
    calls their mother "Speaker 1". Whether names appear is a *condition* (have
    you enrolled anyone), so the only thing the flag could do was be wrong, and
    it was: the captions page stopped sending it and recognition silently
    stopped working.

    An empty gallery still clusters voices, which is what keeps one person as
    Speaker 1 instead of drifting to 2 and 3; enrolment only turns "the same
    person" into "Mom". Captions must never break because naming can't run.
    """
    if not token:
        return []
    try:
        profiles = await load_profiles(token)
        logger.info("transcribe_naming client=%s profiles=%d", client, len(profiles))
        return profiles
    except Exception:
        logger.warning("transcribe_profiles_load_failed client=%s", client)
        return []

