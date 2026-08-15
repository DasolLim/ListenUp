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

# Speech runs at roughly 870 characters per minute (SUBSCRIPTION.md §2), so this
# converts billed characters into the seconds the cloud read-aloud allowance is
# denominated in. Approximate by nature — the allowance is a cost ceiling, not a
# stopwatch — and it errs slightly high, which favours the user.
CHARS_PER_SECOND = 870 / 60


def browser_service():
    """The free tier, always available.

    Constructed directly rather than through the factory: `TTS_SERVICE` picks
    the *cloud* provider for a deployment, and reading it here is what broke
    read-aloud. Turning ElevenLabs on replaced the catalogue instead of adding
    to it, so a Free or Basic user — who cannot use cloud voices at all — was
    left with no voices whatsoever, and Pro spent its 30-minute allowance on
    lines a browser would have read for nothing.

    Browser voices cost nothing, work offline and need no account, so they are
    the floor for every tier and every deployment.
    """
    from services.tts.browser import BrowserTtsService

    return BrowserTtsService()


def cloud_service():
    """The paid tier, or None when this deployment has no cloud provider."""
    service = get_tts_service()
    return service if getattr(service, "renders_audio", False) else None


async def cloud_caller(
    credentials: HTTPAuthorizationCredentials | None,
):
    """Resolve a caller allowed to spend cloud read-aloud, or refuse.

    Only reached when the configured service actually renders audio. Browser
    voices never come through here, which is what keeps read-aloud free on every
    tier — the free thing stays free without an auth round-trip.
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
    # Browser voices first and always; cloud voices are *added* when the
    # deployment has a provider, never substituted for them.
    try:
        voices = list(await browser_service().voices(language))
        cloud = cloud_service()
        if cloud is not None:
            voices.extend(await cloud.voices(language))
    except TtsError as exc:
        raise HTTPException(400, str(exc)) from exc

    if credentials is not None:
        try:
            owned = await rest(
                "GET",
                "custom_voices",
                credentials.credentials,
                params={"select": "display_name,provider_voice_id,language"},
            )
            if owned.status_code == 200:
                voices.extend(
                    _voice_from_row(row)
                    for row in owned.json()
                    if language is None or row.get("language") == language
                )
        except Exception:
            # A custom-voice lookup must never take the preset list down with it:
            # live captions and translation both depend on this endpoint, and a
            # missing table or an expired token should cost you your own voices,
            # not the ability to speak at all.
            logger.warning("custom_voice_list_failed", exc_info=True)

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

    The gate is asymmetric on purpose: browser voices are free on every tier and
    need no sign-in, while cloud rendering is billed per character and so needs
    a Pro caller with allowance left. Asking the *service* whether it renders
    audio (rather than reading TTS_SERVICE here) means a future provider can't
    be added past the paywall by accident.
    """
    # Route on the voice the user actually picked, not on a deployment-wide
    # switch. A browser voice is free on every tier and needs no account even
    # when a cloud provider is configured; only a cloud voice is gated.
    browser = browser_service()
    cloud = cloud_service()
    browser_ids = {voice.id for voice in await browser.voices()}
    cloud_ids = {voice.id for voice in await cloud.voices()} if cloud is not None else set()
    # An id we don't recognise — a stale value in localStorage, a custom voice
    # that was deleted — resolves to the *free* tier, never the paid one.
    # Falling through to cloud would meet a stale preference with a paywall or a
    # bill, which is the wrong way round for a guess.
    use_cloud = request.voice_id in cloud_ids
    if request.voice_id not in browser_ids and not use_cloud:
        logger.info("tts_unknown_voice id=%r — falling back to a browser voice", request.voice_id)

    service = cloud if use_cloud else browser
    who = await cloud_caller(credentials) if use_cloud else None
    try:
        # Only pass expressiveness to services that render audio; the browser
        # tier's signature stays two-argument because it has nothing to apply it
        # to (the client speaks locally).
        shapeable = getattr(service, "supports_expressiveness", False)
        if request.expressiveness is not None and shapeable:
            result = await service.speak(
                request.text, request.voice_id, expressiveness=request.expressiveness
            )
        else:
            result = await service.speak(request.text, request.voice_id)
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
    _, token = user
    response = await rest(
        "GET",
        "custom_voices",
        token,
        params={"select": "id,display_name,provider_voice_id,language,created_at"},
    )
    if response.status_code != 200:
        # A missing migration is the likeliest cause and used to surface as a
        # generic 502, sending people hunting through server logs. Postgrest
        # reports PGRST205 when the table isn't in the schema cache.
        body = response.text or ""
        missing_table = "PGRST205" in body or (
            response.status_code == 404 and "custom_voices" in body
        )
        if missing_table:
            raise HTTPException(
                503,
                "Custom voices aren't set up on this deployment yet: the "
                "custom_voices table is missing. Preset voices still work.",
            )
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

    # Cloning is a Pro capability. Checked after consent so the biometric gate
    # stays first — being on the wrong plan is a billing problem, but recording
    # someone without their agreement is a legal one, and the order of these two
    # checks is the order of their seriousness.
    from app.routes.billing import plan_for_row

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
