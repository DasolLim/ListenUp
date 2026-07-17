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

from services.assemblyai import AudioFormatError, TranscriptSegment
from services.assemblyai.factory import get_transcription_service

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


def _segment_payload(segment: TranscriptSegment, label: str) -> str:
    return json.dumps(
        {
            "type": "segment",
            "speaker": label,
            "text": segment.text,
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "isFinal": segment.is_final,
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

    async def pump_segments() -> None:
        async for segment in service.segments():
            payload = _segment_payload(segment, mapper.label(segment.speaker))
            await _queue_put_with_backpressure(send_queue, payload, segment.is_final)
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
                await service.send_audio(data)
            elif (text := message.get("text")) is not None:
                if json.loads(text).get("type") == "stop":
                    await service.stop()
                    await asyncio.wait_for(send_task, timeout=10)
                    break
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
