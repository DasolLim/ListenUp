"""WebSocket transcription gateway: mic chunks in, diarized caption JSON out.

Client protocol:
  1. First message (text): {"sampleRate": 16000, "encoding": "pcm_s16le"}
     (optional "fixture" is honored only by the mock service, for tests)
  2. Then binary frames of s16le PCM audio, 100–250 ms each.
  3. Optional {"type": "stop"} for a graceful end (flushes remaining segments).

Server messages:
  {"type": "ready"}
  {"type": "segment", "speaker": "Speaker 1", "text": …, "start": s, "end": s, "isFinal": bool}
  {"type": "error", "message": …}
  {"type": "done"}
"""

import asyncio
import json
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.naming import SessionNamer, load_profiles
from app.supa import verify_user
from services.assemblyai import AudioFormatError, TranscriptSegment
from services.assemblyai.factory import get_transcription_service
from services.speaker_id.matcher import SpeakerMatcher

logger = logging.getLogger("listenup.ws.transcribe")

router = APIRouter()

# INTRODUCTION §5: cap at 4–5 speakers. Four named lanes (matching the four
# speaker tints in the UI) + everyone past the cap collapses into "Other".
NAMED_SPEAKER_CAP = 4
SEND_QUEUE_LIMIT = 64


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
    service = get_transcription_service()

    # Enhanced mode: authenticated sessions match diarized speakers to the
    # user's saved voice profiles. Failure to authenticate degrades to generic
    # labels — captions must never break because naming can't run.
    namer: SessionNamer | None = None
    user_token: str | None = None
    if config.get("enhanced") and config.get("token"):
        try:
            await verify_user(str(config["token"]))
            user_token = str(config["token"])
            profiles = await load_profiles(user_token)
            namer = SessionNamer(SpeakerMatcher(profiles))
            logger.info("transcribe_enhanced client=%s profiles=%d", client, len(profiles))
        except Exception:
            logger.warning("transcribe_enhanced_auth_failed client=%s", client)

    try:
        await service.start(
            sample_rate=int(config.get("sampleRate", 0)),
            encoding=str(config.get("encoding", "")),
        )
    except AudioFormatError as exc:
        logger.warning("transcribe_bad_format client=%s error=%s", client, exc)
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close(code=1003)
        return

    logger.info("transcribe_start client=%s service=%s", client, type(service).__name__)
    await websocket.send_text(json.dumps({"type": "ready"}))

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
            # Name resolved (or corrected): relabel this speaker's PAST bubbles too.
            if name is not None and announced.get(label) != name:
                announced[label] = name
                await send_queue.put(
                    json.dumps({"type": "speakerUpdate", "speaker": label, "speakerName": name})
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
        logger.info("transcribe_end client=%s chunks=%d", client, chunks)
