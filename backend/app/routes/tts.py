"""Text-to-speech: read translated text aloud so the other person hears their
own language, instead of the user having to read it out.

  GET  /tts/voices          — selectable voices (public; browser tier needs no key)
  POST /tts/speak           — synthesise text (public for preset voices)
  GET  /tts/custom-voices   — the account's cloned voices (auth)
  POST /tts/custom-voices   — clone a voice from a CONSENTED recording (auth)
  DELETE /tts/custom-voices/{id} — delete a cloned voice everywhere (auth)

This module is the HTTP surface. Which service speaks a given voice lives in
`services.tts.library`; the consent gate, the cap and keeping our rows in step
with the provider live in `app.custom_voices` — where they are reachable without
an HTTP request and cannot be routed around by a second create path.
"""

import base64
import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.custom_voices import CustomVoiceStore
from app.supa import rest, verify_user
from services.tts import (
    VOICE_CLONE_CONSENT_TEXT,
    VOICE_CLONE_CONSENT_VERSION,
    TtsError,
)
from services.tts.library import VoiceLibrary

if TYPE_CHECKING:  # imported lazily at runtime to avoid a route-module cycle
    from app.routes.billing import Caller

logger = logging.getLogger("listenup.tts")

router = APIRouter(prefix="/tts")
bearer = HTTPBearer(auto_error=False)

# Speech runs at roughly 870 characters per minute (docs/product/SUBSCRIPTION.md §2), so this
# converts billed characters into the seconds the cloud read-aloud allowance is
# denominated in. Approximate by nature — the allowance is a cost ceiling, not a
# stopwatch — and it errs slightly high, which favours the user.
CHARS_PER_SECOND = 870 / 60


async def cloud_caller(credentials: HTTPAuthorizationCredentials | None) -> "Caller":
    """Resolve a caller allowed to spend cloud read-aloud, or refuse.

    Only reached for a voice the library says is billable. Browser voices never
    come through here, which is what keeps read-aloud free on every tier — the
    free thing stays free without an auth round-trip.
    """
    from app.routes.billing import _refusal, caller_for_token

    if credentials is None:
        raise HTTPException(401, "Sign in to use cloud voices.")
    who = await caller_for_token(credentials.credentials)

    spent = who.allowance("cloud_tts")
    if spent.blocked:
        raise _refusal(who, spent)
    return who


async def auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tuple[str, str]:
    if credentials is None:
        raise HTTPException(401, "Sign in to manage custom voices.")
    token = credentials.credentials
    return await verify_user(token), token


def store(user: tuple[str, str]) -> CustomVoiceStore:
    user_id, token = user
    return CustomVoiceStore(token, user_id, VoiceLibrary.configured())


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice_id: str = Field(min_length=1, max_length=120)
    # How much the voice varies its delivery. Rendered by the provider, so it
    # must arrive with the request; browser voices ignore it. Optional so older
    # clients and the free tier keep working unchanged.
    expressiveness: float | None = Field(default=None, ge=0.0, le=1.0)


@router.get("/voices")
async def list_voices(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    language: str | None = None,
) -> dict:
    """Selectable voices, plus the consent copy the clone flow must display.

    Auth is optional on purpose. Browser voices need no account, so this stays
    public — but a signed-in caller also gets the voices they have recorded.
    Without that, cloning was a dead end: a voice could be created, listed in the
    studio and deleted, yet never appear in a picker, so it could never actually
    be spoken with.
    """
    library = VoiceLibrary.configured()
    try:
        voices = await library.catalogue(language)
    except TtsError as exc:
        raise HTTPException(400, str(exc)) from exc

    if credentials is not None:
        owned = CustomVoiceStore(credentials.credentials, "", library)
        voices.extend(await owned.voices(language))

    return {
        "voices": [v.to_dict() for v in voices],
        "consent_text": VOICE_CLONE_CONSENT_TEXT,
        "consent_version": VOICE_CLONE_CONSENT_VERSION,
    }


@router.post("/speak")
async def speak(
    request: SpeakRequest,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> dict:
    """Render text in a voice.

    Browser voices return `speak_locally: true` and no audio — the client speaks
    them with `speechSynthesis`. Cloud voices return base64 audio. One response
    shape for both so the frontend has a single code path.

    The gate is asymmetric on purpose, and it runs on the *voice* rather than on
    a deployment-wide switch: browser voices are free on every tier and need no
    sign-in even where a cloud provider is configured, while cloud rendering is
    billed per character and needs a Pro caller with allowance left.
    """
    library = VoiceLibrary.configured()
    billable = await library.is_billable(request.voice_id)
    who = await cloud_caller(credentials) if billable else None

    try:
        result = await library.speak(
            request.text, request.voice_id, request.expressiveness
        )
    except TtsError as exc:
        # 503, not 500: the caption/translation is already on screen, so this is
        # a degraded-but-recoverable state, and the client falls back to a
        # browser voice.
        raise HTTPException(503, str(exc)) from exc

    # Cached audio is replayed from Redis and costs nothing, so it spends no
    # allowance — replaying a line you already heard should always be free.
    if who is not None and not result.cached and result.characters:
        await who.record("cloud_tts", max(1, round(result.characters / CHARS_PER_SECOND)))

    return {
        "voice_id": result.voice_id,
        "speak_locally": result.speak_locally,
        "audio_base64": base64.b64encode(result.audio).decode() if result.audio else "",
        "mime_type": result.mime_type,
        "characters": result.characters,
        "cached": result.cached,
    }


@router.get("/custom-voices")
async def list_custom_voices(user: Annotated[tuple[str, str], Depends(auth)]) -> list[dict]:
    return await store(user).rows()


@router.post("/custom-voices", status_code=201)
async def create_custom_voice(
    user: Annotated[tuple[str, str], Depends(auth)],
    display_name: Annotated[str, Form()],
    consent_given: Annotated[bool, Form()],
    consented_by: Annotated[str, Form()],
    sample: UploadFile,
    language: Annotated[str, Form()] = "en",
) -> dict:
    """Clone a voice from a recording — only with the speaker's consent.

    Cloning is a Pro capability, checked *after* consent so the biometric gate
    stays first: being on the wrong plan is a billing problem, but recording
    someone without their agreement is a legal one, and the order of these two
    checks is the order of their seriousness.
    """
    if not consent_given or not consented_by.strip():
        raise HTTPException(
            400,
            "Consent is required: the person being recorded must agree before ListenUp can "
            "build a voice from their speech. Their voice is biometric data.",
        )
    await _assert_may_clone(user)
    return await store(user).create(
        display_name=display_name,
        sample=await sample.read(),
        language=language,
        consent_given=consent_given,
        consented_by=consented_by,
    )


async def _assert_may_clone(user: tuple[str, str]) -> None:
    from app.routes.billing import plan_for_row

    user_id, token = user
    subscription = await rest(
        "GET", "subscriptions", token, params={"user_id": f"eq.{user_id}", "select": "*"}
    )
    rows = subscription.json() if subscription.status_code == 200 else []
    plan = plan_for_row(rows[0] if rows else {})
    if not plan.voice_cloning:
        raise HTTPException(
            402,
            {
                "reason": "not_included",
                "metric": "voice_cloning",
                "plan": plan.tier,
                "upgradeTo": "pro",
                "message": "Recording your own voice is part of Pro.",
            },
        )


@router.delete("/custom-voices/{voice_id}", status_code=204)
async def delete_custom_voice(
    voice_id: str, user: Annotated[tuple[str, str], Depends(auth)]
) -> None:
    """Delete a cloned voice from our records and from the provider."""
    await store(user).delete(voice_id)
