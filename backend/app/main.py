import logging
import os
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.env import load_env
from app.routes.feedback import router as feedback_router
from app.routes.profiles import router as profiles_router
from app.routes.transcribe import router as transcribe_router
from app.routes.translate import router as translate_router
from services.speaker_id import get_speaker_embedder

# Root .env first (shell env wins) — services read os.environ lazily.
load_env()

# No-op without a DSN: sentry_sdk.init is only called when SENTRY_DSN is set.
if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("listenup.ws")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load the speaker-ID model once at startup (never per request).
    get_speaker_embedder().load()
    yield


app = FastAPI(title="ListenUp API", lifespan=lifespan)
app.include_router(transcribe_router)
app.include_router(feedback_router)
app.include_router(profiles_router)
app.include_router(translate_router)

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/echo")
async def ws_echo(websocket: WebSocket) -> None:
    await websocket.accept()
    client = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
    logger.info("ws_connect client=%s path=/ws/echo", client)
    messages = 0
    try:
        while True:
            text = await websocket.receive_text()
            messages += 1
            logger.info("ws_message client=%s n=%d bytes=%d", client, messages, len(text))
            await websocket.send_text(text)
    except WebSocketDisconnect as exc:
        logger.info("ws_disconnect client=%s code=%s messages=%d", client, exc.code, messages)
