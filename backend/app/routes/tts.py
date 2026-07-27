"""Text-to-speech: read translated text aloud so the other person hears their
own language, instead of the user having to read it out.

  GET  /tts/voices          — selectable voices (public; browser tier needs no key)
  POST /tts/speak           — synthesise text (public for preset voices)
  GET  /tts/custom-voices   — the account's cloned voices (auth)
  POST /tts/custom-voices   — clone a voice from a CONSENTED recording (auth)
  DELETE /tts/custom-voices/{id} — delete a cloned voice everywhere (auth)

Custom voices are biometric data, so the same rules as Phase 3 enrollment apply
and are enforced here rather than in the UI:
  - no consent record from the voice owner → nothing is created (400)
  - too little audio → blocked with guidance (400)
  - delete removes our row AND the provider-side voice
"""

import base64
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.supa import rest, verify_user
from services.speaker_id.base import audio_seconds
from services.tts import (
    VOICE_CLONE_CONSENT_TEXT,
    VOICE_CLONE_CONSENT_VERSION,
    TtsError,
    Voice,
    get_tts_service,
)

logger = logging.getLogger("listenup.tts")

router = APIRouter(prefix="/tts")
bearer = HTTPBearer(auto_error=False)

# A person can hold a handful of cloned voices; this is a product cap, not a
# provider limit, and it keeps the picker readable.
MAX_CUSTOM_VOICES = 4


async def auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tuple[str, str]:
    if credentials is None:
        raise HTTPException(401, "Sign in to manage custom voices.")
    token = credentials.credentials
    return await verify_user(token), token


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice_id: str = Field(min_length=1, max_length=120)


@router.get("/voices")
async def list_voices(language: str | None = None) -> dict:
    """Preset voices, plus the consent copy the clone flow must display."""
    service = get_tts_service()
    try:
        voices = await service.voices(language)
    except TtsError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "voices": [v.to_dict() for v in voices],
        "consent_text": VOICE_CLONE_CONSENT_TEXT,
        "consent_version": VOICE_CLONE_CONSENT_VERSION,
    }


@router.post("/speak")
async def speak(request: SpeakRequest) -> dict:
    """Render text in a voice.

    Browser voices return `speak_locally: true` and no audio — the client speaks
    them with `speechSynthesis`. Cloud voices return base64 audio. One response
    shape for both so the frontend has a single code path.
    """
    service = get_tts_service()
    try:
        result = await service.speak(request.text, request.voice_id)
    except TtsError as exc:
        # 503, not 500: the caption/translation is already on screen, so this is
        # a degraded-but-recoverable state, and the client falls back to a
        # browser voice.
        raise HTTPException(503, str(exc)) from exc

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
    _, token = user
    response = await rest(
        "GET",
        "custom_voices",
        token,
        params={"select": "id,display_name,provider_voice_id,language,created_at"},
    )
    if response.status_code != 200:
        raise HTTPException(502, "Could not load your custom voices.")
    return response.json()


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

    The consent gate is deliberately first: a cloned voice can say things the
    person never said, so creating one without their agreement is impersonation.
    """
    user_id, token = user

    if not consent_given or not consented_by.strip():
        raise HTTPException(
            400,
            "Consent is required: the person being recorded must agree before ListenUp can "
            "build a voice from their speech. Their voice is biometric data.",
        )

    existing = await rest("GET", "custom_voices", token, params={"select": "id"})
    if existing.status_code == 200 and len(existing.json()) >= MAX_CUSTOM_VOICES:
        raise HTTPException(
            400,
            f"You already have {MAX_CUSTOM_VOICES} custom voices. Delete one to add another.",
        )

    raw = await sample.read()
    seconds = audio_seconds(raw)

    service = get_tts_service()
    clone = getattr(service, "clone_voice", None)
    if clone is None:
        raise HTTPException(
            400,
            "Custom voices need the cloud voice provider. Ask an admin to enable it "
            "(TTS_SERVICE=elevenlabs); preset voices keep working meanwhile.",
        )

    try:
        provider_voice_id = await clone(display_name.strip(), raw, seconds)
    except TtsError as exc:
        raise HTTPException(400, str(exc)) from exc

    insert = await rest(
        "POST",
        "custom_voices",
        token,
        json={
            "owner_user_id": user_id,
            "display_name": display_name.strip(),
            "provider_voice_id": provider_voice_id,
            "language": language,
            "consented_by": consented_by.strip(),
            "consent_text_version": VOICE_CLONE_CONSENT_VERSION,
        },
    )
    if insert.status_code not in (200, 201):
        # Don't leave an orphan at the provider if our row failed to save.
        delete = getattr(service, "delete_voice", None)
        if delete is not None:
            try:
                await delete(provider_voice_id)
            except TtsError:
                logger.warning("tts_orphan_voice provider_voice=%s", provider_voice_id)
        raise HTTPException(502, "Could not save that voice. Nothing was kept.")

    logger.info(
        "tts_custom_voice_created name=%r seconds=%.1f consent_version=%s",
        display_name, seconds, VOICE_CLONE_CONSENT_VERSION,
    )
    return {"display_name": display_name.strip(), "language": language}


@router.delete("/custom-voices/{voice_id}", status_code=204)
async def delete_custom_voice(
    voice_id: str, user: Annotated[tuple[str, str], Depends(auth)]
) -> None:
    """Delete a cloned voice from our records and from the provider."""
    _, token = user
    lookup = await rest(
        "GET",
        "custom_voices",
        token,
        params={"id": f"eq.{voice_id}", "select": "provider_voice_id"},
    )
    if lookup.status_code != 200 or not lookup.json():
        raise HTTPException(404, "That voice no longer exists.")
    provider_voice_id = lookup.json()[0]["provider_voice_id"]

    service = get_tts_service()
    delete = getattr(service, "delete_voice", None)
    if delete is not None:
        try:
            await delete(provider_voice_id)
        except TtsError as exc:
            # Our row stays so the user can retry rather than losing the handle
            # to a voice that still exists at the provider.
            raise HTTPException(502, str(exc)) from exc

    removed = await rest("DELETE", "custom_voices", token, params={"id": f"eq.{voice_id}"})
    if removed.status_code not in (200, 204):
        raise HTTPException(502, "Could not delete that voice. Try again.")
    logger.info("tts_custom_voice_deleted voice=%s", voice_id)


def _voice_from_row(row: dict) -> Voice:
    """Adapt a stored custom voice into the same shape as a preset."""
    return Voice(
        id=row["provider_voice_id"],
        label=f"{row['display_name']} (custom)",
        language=row.get("language", "en"),
        gender="neutral",
        provider="custom",
        owner_name=row["display_name"],
    )
