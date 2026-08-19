"""WebSocket transcription gateway: mic chunks in, diarized caption JSON out.

This module is the *wire*. What a session means — who is speaking, what the
client is told, what it costs — lives in `app.caption_session`, so those
decisions can be tested without opening a socket and this file stays readable
as the protocol it implements.

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
  {"type": "speakerMerge", "from": "Speaker 2", "to": "Speaker 1"}
      Later audio showed two speakers were one person; relabel what is already
      on screen. Live diarization commits with no lookahead, so this is how a
      decision made on the first second of a voice gets corrected.
  {"type": "error", "message": …}
  {"type": "done"}
"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.caption_session import CaptionSession, Frame, SessionRefused
from services.assemblyai.base import BATCH_LANGUAGES, SPOKEN_LANGUAGES

logger = logging.getLogger("listenup.ws.transcribe")

router = APIRouter()

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


class SendQueue:
    """Bounded outbound queue that sheds the right frames under pressure.

    When a slow client falls behind, interim segments are dropped — they are
    superseded by the next one anyway — and finals are kept, because a final is
    the only record of a sentence. Which is which is the frame's own answer
    (`Frame.droppable`); this used to be decided by searching the encoded JSON
    for `"isFinal": true`, a caption decision written in the vocabulary of a
    serialiser.
    """

    def __init__(self, limit: int = SEND_QUEUE_LIMIT) -> None:
        self._queue: asyncio.Queue[Frame | None] = asyncio.Queue(maxsize=limit)

    async def put(self, frame: Frame) -> None:
        while True:
            try:
                self._queue.put_nowait(frame)
                return
            except asyncio.QueueFull:
                try:
                    dropped = self._queue.get_nowait()
                    if dropped is not None and not dropped.droppable and frame.droppable:
                        # Never displace a final for an interim: put the final
                        # back and drop the incoming interim instead.
                        self._queue.put_nowait(dropped)
                        return
                except asyncio.QueueEmpty:
                    pass

    async def extend(self, frames: list[Frame]) -> None:
        for frame in frames:
            await self.put(frame)

    async def end(self) -> None:
        await self._queue.put(None)

    async def get(self) -> Frame | None:
        return await self._queue.get()


@router.websocket("/ws/transcribe")
async def ws_transcribe(websocket: WebSocket) -> None:
    await websocket.accept()
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "?"

    try:
        config = json.loads(await websocket.receive_text())
    except (json.JSONDecodeError, WebSocketDisconnect):
        await websocket.close(code=1003, reason="expected JSON config as first message")
        return

    try:
        session = await CaptionSession.open(config, client=client)
    except SessionRefused as refusal:
        await websocket.send_text(refusal.frame.encode())
        await websocket.close(code=refusal.code, reason=refusal.reason)
        if refusal.code == 1008:
            logger.info("transcribe_blocked client=%s", client)
        return

    for frame in session.opening_frames:
        await websocket.send_text(frame.encode())

    outbound = SendQueue()

    async def pump_segments() -> None:
        async for segment in session.segments():
            await outbound.extend(await session.observe(segment))
        await outbound.end()

    async def send_loop() -> None:
        while True:
            frame = await outbound.get()
            if frame is None:
                await websocket.send_text(json.dumps({"type": "done"}))
                return
            await websocket.send_text(frame.encode())

    pump_task = asyncio.create_task(pump_segments())
    send_task = asyncio.create_task(send_loop())

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(int(message.get("code") or 1005))
            if (data := message.get("bytes")) is not None:
                await session.push_audio(data)
            elif (text := message.get("text")) is not None:
                parsed = json.loads(text)
                kind = parsed.get("type")
                if kind == "stop":
                    await session.end_input()
                    await asyncio.wait_for(send_task, timeout=10)
                    break
                # Pause and resume are acknowledged rather than applied
                # silently: the client shows "paused" to someone deciding
                # whether it is safe to speak, so the claim has to be about the
                # server's state, not about a frame having been sent.
                if kind == "pause":
                    await outbound.put(await session.pause())
                elif kind == "resume":
                    await outbound.put(session.resume())
                elif kind == "correct":
                    await outbound.extend(
                        await session.correct(
                            str(parsed.get("speaker", "")), parsed.get("profileId")
                        )
                    )
    except WebSocketDisconnect as exc:
        logger.info(
            "transcribe_disconnect client=%s code=%s chunks=%d",
            client, exc.code, session.cost.chunks,
        )
    except TimeoutError:
        logger.warning("transcribe_flush_timeout client=%s", client)
    finally:
        for task in (pump_task, send_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(pump_task, send_task, return_exceptions=True)
        await session.close()
