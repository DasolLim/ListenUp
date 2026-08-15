"""WebSocket transcription gateway: mic chunks in, diarized caption JSON out.

Client protocol:
  1. First message (text): {"sampleRate": 16000, "encoding": "pcm_s16le"}
     (optional "fixture" is honored only by the mock service, for tests)
  2. Then binary frames of s16le PCM audio, 100–250 ms each.
  3. Optional {"type": "pause"} / {"type": "resume"} to hold the session open
     while no audio is being sent. Paused time is billed to nobody and excluded
     from caption-lag telemetry (see SessionClock).
  4. Optional {"type": "stop"} for a graceful end (flushes remaining segments).

Server messages:
  {"type": "ready"}
  {"type": "segment", "speaker": "Speaker 1", "text": …, "start": s, "end": s, "isFinal": bool}
  {"type": "paused"} / {"type": "resumed"}   (acknowledgements)
  {"type": "error", "message": …}
  {"type": "done"}
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.naming import SessionNamer, load_profiles
from app.session_clock import SessionClock
from app.timing import record
from services.assemblyai import AudioFormatError, TranscriptSegment
from services.assemblyai.base import (
    BATCH_LANGUAGES,
    SPOKEN_LANGUAGES,
    UnsupportedLanguageError,
    assert_spoken_language,
)
from services.assemblyai.factory import get_transcription_service
from services.speaker_id.matcher import SpeakerMatcher

logger = logging.getLogger("listenup.ws.transcribe")

router = APIRouter()


# INTRODUCTION §5: cap at 4–5 speakers. Four named lanes (matching the four
# speaker tints in the UI) + everyone past the cap collapses into "Other".
NAMED_SPEAKER_CAP = 4
SEND_QUEUE_LIMIT = 64


@router.get("/transcribe/languages")
def spoken_languages() -> dict:
    """Languages the mic can be captioned in, and how each is transcribed.
    'batch' languages lag a few seconds (no streaming model exists for them)."""
    return {
        "languages": SPOKEN_LANGUAGES,
        "modes": {
            code: ("batch" if code in BATCH_LANGUAGES else "streaming")
            for code in SPOKEN_LANGUAGES
        },
    }


class SpeakerMapper:
    """Stable provider-label → display-label mapping, capped."""

    def __init__(self) -> None:
        self._order: dict[str, str] = {}

    def label(self, raw: str) -> str:
        if raw not in self._order:
            if len(self._order) < NAMED_SPEAKER_CAP:
                self._order[raw] = f"Speaker {len(self._order) + 1}"
            else:
                self._order[raw] = "Other"
        return self._order[raw]

    def raw_for(self, label: str) -> str | None:
        for raw, mapped in self._order.items():
            if mapped == label:
                return raw
        return None


def _segment_payload(
    segment: TranscriptSegment, label: str, speaker_name: str | None = None
) -> str:
    return json.dumps(
        {
            "type": "segment",
            "speaker": label,
            "speakerName": speaker_name,
            "text": segment.text,
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "isFinal": segment.is_final,
            "turnId": segment.turn_id,
        }
    )


async def _queue_put_with_backpressure(
    queue: asyncio.Queue[str | None], payload: str, is_final: bool
) -> None:
    """Bounded queue: when a slow client falls behind, shed interim segments
    (they'll be superseded anyway) and keep finals."""
    while True:
        try:
            queue.put_nowait(payload)
            return
        except asyncio.QueueFull:
            try:
                dropped = queue.get_nowait()
                if dropped is not None and '"isFinal": true' in dropped and not is_final:
                    # Never displace a final for an interim: re-queue the final,
                    # drop the incoming interim instead.
                    queue.put_nowait(dropped)
                    return
            except asyncio.QueueEmpty:
                pass


async def _apply_correction(
    parsed: dict,
    namer: SessionNamer,
    mapper: "SpeakerMapper",
    send_queue: asyncio.Queue[str | None],
    user_token: str | None,
) -> None:
    """Tap-to-correct: remap the session label now, and append this speaker's
    buffered audio as a correction embedding so the profile improves."""
    from app.supa import rest
    from services.speaker_id import get_speaker_embedder
    from services.speaker_id.matcher import Match

    label = str(parsed.get("speaker", ""))
    raw = mapper.raw_for(label)
    if raw is None:
        return
    profile_id = parsed.get("profileId")

    if profile_id is None:
        namer.set_name(raw, None)
        await send_queue.put(
            json.dumps({"type": "speakerUpdate", "speaker": label, "speakerName": None})
        )
        logger.info("correction_applied label=%s -> unknown", label)
        return

    profile = next((p for p in namer.matcher.profiles if p.profile_id == profile_id), None)
    if profile is None:
        return
    namer.set_name(raw, Match(profile.profile_id, profile.display_name, 1.0))
    await send_queue.put(
        json.dumps(
            {"type": "speakerUpdate", "speaker": label, "speakerName": profile.display_name}
        )
    )

    pcm = namer.speaker_audio(raw)
    if user_token and len(pcm) >= 16000:  # ≥0.5 s of audio to learn from
        try:
            embedding = await asyncio.to_thread(get_speaker_embedder().embed, pcm, 16000)
            response = await rest(
                "POST",
                "speaker_embeddings",
                user_token,
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
            logger.info("correction_applied label=%s -> %s (audio too short to learn)",
                        label, profile.display_name)


@router.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket) -> None:
    await websocket.accept()
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "?"

    try:
        config = json.loads(await websocket.receive_text())
    except (json.JSONDecodeError, WebSocketDisconnect):
        await websocket.close(code=1003, reason="expected JSON config as first message")
        return

    fixture = config.get("fixture")
    if fixture and os.environ.get("TRANSCRIPTION_SERVICE", "mock").lower() == "mock":
        os.environ["MOCK_FIXTURE"] = str(fixture)

    language = str(config.get("language") or "en").lower()
    try:
        assert_spoken_language(language)
    except UnsupportedLanguageError as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close(code=1003)
        return
    service = get_transcription_service(language)

    # A token is now resolved whenever one is sent, not only in enhanced mode:
    # caption *minutes* are metered on every tier, so the session needs to know
    # who it belongs to even when no speaker naming is requested.
    namer: SessionNamer | None = None
    user_token: str | None = None
    who = None
    if config.get("token"):
        try:
            from app.routes.billing import caller_for_token

            who = await caller_for_token(str(config["token"]))
            user_token = str(config["token"])
        except Exception:
            # Failure here degrades to an unmetered, unnamed session rather than
            # refusing to caption. Captions are the accessibility core; a
            # billing lookup that times out must never be the reason someone
            # can't follow a conversation.
            logger.warning("transcribe_auth_failed client=%s", client)

    # The caption allowance is checked *before* the session starts and never
    # again. That is the whole design: a cap that fires mid-sentence can fire in
    # a medical appointment, so it blocks the next start instead and the session
    # already running always finishes.
    if who is not None:
        spent = who.allowance("captions")
        if spent.blocked:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "reason": "limit_reached",
                        "metric": "captions",
                        "plan": who.plan.tier,
                        "resetsAt": who.usage.period_end,
                        "upgradeTo": "basic" if who.plan.tier == "free" else "pro",
                        "message": (
                            "You've used all your caption hours for this billing period."
                        ),
                    }
                )
            )
            await websocket.close(code=1008, reason="caption allowance reached")
            logger.info("transcribe_blocked client=%s tier=%s", client, who.plan.tier)
            return
        if spent.warning:
            # Warn once, at the start, so the user can decide how to spend what
            # is left rather than discovering the cap when it arrives.
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "usage",
                        "metric": "captions",
                        "used": spent.used,
                        "limit": spent.limit,
                        "remaining": spent.remaining,
                        "resetsAt": who.usage.period_end,
                    }
                )
            )

    # Speaker naming runs for every authenticated session, not behind a flag.
    #
    # It used to require `enhanced: true` from the client, which made naming a
    # product choice. It never was one: nobody knowingly picks the version that
    # calls their mother "Speaker 1". Whether names appear is a *condition* —
    # have you enrolled anyone — so the only thing the flag could do was be
    # wrong, and it was: the captions page stopped sending it during the tool
    # consolidation and speaker recognition silently stopped working.
    #
    # With no enrolled profiles `SpeakerMatcher` simply never matches, which is
    # the same generic-label outcome as before at the cost of one query.
    if user_token:
        try:
            profiles = await load_profiles(user_token)
            namer = SessionNamer(SpeakerMatcher(profiles))
            logger.info("transcribe_naming client=%s profiles=%d", client, len(profiles))
        except Exception:
            # Captions must never break because naming can't run.
            logger.warning("transcribe_profiles_load_failed client=%s", client)

    try:
        await service.start(
            sample_rate=int(config.get("sampleRate", 0)),
            encoding=str(config.get("encoding", "")),
            language=language,
        )
    except AudioFormatError as exc:
        logger.warning("transcribe_bad_format client=%s error=%s", client, exc)
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close(code=1003)
        return

    # Korean has no streaming model, so it runs in buffered (batch) mode — the UI
    # tells the user captions arrive a few seconds behind instead of instantly.
    mode = "batch" if language in BATCH_LANGUAGES else "streaming"
    logger.info(
        "transcribe_start client=%s service=%s language=%s mode=%s",
        client, type(service).__name__, language, mode,
    )
    await websocket.send_text(json.dumps({"type": "ready", "language": language, "mode": mode}))

    # The clock starts once captioning actually begins. A session rejected for a
    # bad audio format or an exhausted allowance never reaches here, so it costs
    # the user nothing. It stops again whenever the user pauses, so holding the
    # socket open between two halves of a conversation is free.
    clock = SessionClock()

    send_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=SEND_QUEUE_LIMIT)
    mapper = SpeakerMapper()

    announced: dict[str, str] = {}

    async def pump_segments() -> None:
        async for segment in service.segments():
            name = None
            if namer is not None:
                match = await namer.observe(segment)
                name = match.display_name if match else None
            label = mapper.label(segment.speaker)
            payload = _segment_payload(segment, label, name)
            await _queue_put_with_backpressure(send_queue, payload, segment.is_final)

            # Caption lag as the *user* experiences it: how far behind the spoken
            # moment this caption landed. Measured here rather than inside each
            # service because all three implementations converge on this queue —
            # instrumenting them separately would be three chances to miss one,
            # and the streaming path would have silently reported nothing.
            #
            # `stage` separates this from the batch API round trip, which is the
            # same name but a different measurement; mixing them under one name
            # would corrupt the aggregate.
            if segment.is_final:
                # `clock.elapsed()` rather than raw wall time: `segment.end` is a
                # position in the audio timeline, which does not advance while
                # paused. Subtracting one from the other without excluding the
                # pause would report every caption after it as arriving late by
                # the length of the pause.
                lag_ms = (clock.elapsed() - segment.end) * 1000
                record(
                    "stt_window",
                    max(0.0, lag_ms),
                    language=language,
                    mode=mode,
                    stage="caption",
                    named=name is not None,
                )
            # Name resolved: fill in this speaker's earlier bubbles that were
            # still unnamed. `fillOnly` matters now that a label can carry
            # different people over a session — without it, naming the current
            # turn would rewrite the previous speaker's history under the same
            # label. Bubbles already carry their own per-turn name.
            if name is not None and announced.get(label) != name:
                announced[label] = name
                await send_queue.put(
                    json.dumps(
                        {
                            "type": "speakerUpdate",
                            "speaker": label,
                            "speakerName": name,
                            "fillOnly": True,
                        }
                    )
                )
        await send_queue.put(None)

    async def send_loop() -> None:
        while True:
            payload = await send_queue.get()
            if payload is None:
                await websocket.send_text(json.dumps({"type": "done"}))
                return
            await websocket.send_text(payload)

    pump_task = asyncio.create_task(pump_segments())
    send_task = asyncio.create_task(send_loop())

    chunks = 0
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(int(message.get("code") or 1005))
            if (data := message.get("bytes")) is not None:
                # Audio arriving while paused is dropped rather than
                # transcribed. The client stops sending on pause, so this only
                # catches frames already in flight when the pause was sent —
                # but "paused" has to mean nothing is transcribed, or the
                # promise the button makes is not one the server keeps.
                if clock.paused:
                    continue
                chunks += 1
                if namer is not None:
                    namer.add_audio(data)
                await service.send_audio(data)
            elif (text := message.get("text")) is not None:
                parsed = json.loads(text)
                if parsed.get("type") == "stop":
                    await service.stop()
                    await asyncio.wait_for(send_task, timeout=10)
                    break
                # Acknowledged rather than applied silently. The client shows
                # "paused" to someone who is deciding whether it is safe to
                # speak, so the claim has to be about the server's state, not
                # about a frame having been sent.
                if parsed.get("type") == "pause":
                    clock.pause()
                    # Close the current utterance before the audio stops. On a
                    # buffering transport the half-finished window would
                    # otherwise wait through the pause and be completed by
                    # whatever is said after it — one caption spanning two
                    # moments. No-op on the streaming transports.
                    await service.flush()
                    await send_queue.put(json.dumps({"type": "paused"}))
                    logger.info("transcribe_pause client=%s chunks=%d", client, chunks)
                    continue
                if parsed.get("type") == "resume":
                    clock.resume()
                    await send_queue.put(json.dumps({"type": "resumed"}))
                    logger.info(
                        "transcribe_resume client=%s paused_s=%.1f",
                        client, clock.paused_seconds(),
                    )
                    continue
                if parsed.get("type") == "correct" and namer is not None:
                    await _apply_correction(parsed, namer, mapper, send_queue, user_token)
    except WebSocketDisconnect as exc:
        logger.info("transcribe_disconnect client=%s code=%s chunks=%d", client, exc.code, chunks)
    except TimeoutError:
        logger.warning("transcribe_flush_timeout client=%s", client)
    finally:
        for task in (pump_task, send_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(pump_task, send_task, return_exceptions=True)
        await service.stop()
        # Meter on close rather than on a timer: the number we owe is the length
        # of the session, and recording it once means a dropped connection can't
        # leave a partially-counted session behind. `record` never raises.
        if who is not None:
            # Rounded, not truncated: `int()` always rounds down, so every
            # session would under-count by up to a second and the error would
            # accumulate in one direction across a month. A session that reached
            # `ready` at all costs a real STT connection, so it bills at least
            # one second rather than being free.
            #
            # `clock.elapsed()` excludes time the user spent paused: the socket
            # stays open across a pause so the transcript survives, and billing
            # a held-open session would make the pause button cost the same as
            # not pausing.
            await who.record("captions", max(1, round(clock.elapsed())))
        logger.info(
            "transcribe_end client=%s chunks=%d billed_s=%d paused_s=%.1f",
            client, chunks, max(1, round(clock.elapsed())), clock.paused_seconds(),
        )
