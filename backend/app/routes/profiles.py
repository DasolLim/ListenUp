"""Voice-profile enrollment with a hard consent gate (INTRODUCTION §6).

Biometric rules enforced here, not in the UI:
  - no consent record → nothing persists (400)
  - under 20 s of audio → blocked with guidance (400)
  - delete removes profile + embeddings + consent (DB cascade)
  - export returns everything stored about the person
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.supa import rest, verify_user
from services.speaker_id import MIN_ENROLL_SECONDS, get_speaker_embedder
from services.speaker_id.base import audio_seconds

logger = logging.getLogger("listenup.profiles")

router = APIRouter(prefix="/profiles")

CONSENT_TEXT_VERSION = "2026-07-18.v1"
MAX_ENROLL_SECONDS = 35.0

bearer = HTTPBearer(auto_error=False)


async def auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> tuple[str, str]:
    if credentials is None:
        raise HTTPException(401, "Sign in to manage voice profiles.")
    token = credentials.credentials
    return await verify_user(token), token


@router.get("")
async def list_profiles(user: Annotated[tuple[str, str], Depends(auth)]) -> list[dict]:
    _, token = user
    response = await rest(
        "GET",
        "speaker_profiles",
        token,
        params={"select": "id,display_name,created_at,speaker_embeddings(count)"},
    )
    if response.status_code != 200:
        raise HTTPException(502, "Could not load profiles.")
    return [
        {
            "id": row["id"],
            "display_name": row["display_name"],
            "created_at": row["created_at"],
            "embedding_count": (row.get("speaker_embeddings") or [{}])[0].get("count", 0),
        }
        for row in response.json()
    ]


@router.post("", status_code=201)
async def enroll(
    user: Annotated[tuple[str, str], Depends(auth)],
    display_name: Annotated[str, Form(min_length=1, max_length=60)],
    consent_given: Annotated[bool, Form()],
    consented_by: Annotated[str, Form(max_length=120)],
    audio: UploadFile,
) -> dict:
    user_id, token = user

    # Consent gate FIRST — nothing is computed or stored without it.
    if not consent_given or not consented_by.strip():
        raise HTTPException(
            400,
            "Consent required: the person being enrolled must agree, and their name "
            "must be recorded. Voice profiles are biometric data.",
        )

    pcm = await audio.read()
    seconds = audio_seconds(pcm)
    if seconds < MIN_ENROLL_SECONDS:
        raise HTTPException(
            400,
            f"Recording too short ({seconds:.0f}s). Please record at least "
            f"{MIN_ENROLL_SECONDS:.0f} seconds — have {display_name} read the "
            "enrollment script at a natural pace.",
        )
    if seconds > MAX_ENROLL_SECONDS:
        pcm = pcm[: int(MAX_ENROLL_SECONDS * 32000)]

    embedder = get_speaker_embedder()
    embedding = await asyncio.to_thread(embedder.embed, pcm, 16000)

    profile_response = await rest(
        "POST",
        "speaker_profiles",
        token,
        json={"owner_user_id": user_id, "display_name": display_name.strip()},
        prefer="return=representation",
    )
    if profile_response.status_code != 201:
        raise HTTPException(502, "Could not save the profile.")
    profile_id = profile_response.json()[0]["id"]

    embed_response = await rest(
        "POST",
        "speaker_embeddings",
        token,
        json={"profile_id": profile_id, "embedding": str(embedding), "source": "enrollment"},
    )
    consent_response = await rest(
        "POST",
        "consent_records",
        token,
        json={
            "profile_id": profile_id,
            "consented_by": consented_by.strip(),
            "consent_text_version": CONSENT_TEXT_VERSION,
        },
    )
    if embed_response.status_code != 201 or consent_response.status_code != 201:
        # Keep biometric storage atomic: roll the profile back (cascade).
        await rest("DELETE", f"speaker_profiles?id=eq.{profile_id}", token)
        raise HTTPException(502, "Could not finish enrollment; nothing was saved.")

    logger.info(
        "profile_enrolled user=%s profile=%s seconds=%.0f consent_version=%s",
        user_id, profile_id, seconds, CONSENT_TEXT_VERSION,
    )
    return {"id": profile_id, "display_name": display_name.strip(), "seconds": round(seconds)}


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: str, user: Annotated[tuple[str, str], Depends(auth)]
) -> None:
    user_id, token = user
    response = await rest(
        "DELETE",
        "speaker_profiles",
        token,
        params={"id": f"eq.{profile_id}"},
        prefer="return=representation",
    )
    if response.status_code != 200 or not response.json():
        raise HTTPException(404, "Profile not found.")
    logger.info("profile_deleted user=%s profile=%s", user_id, profile_id)


@router.get("/{profile_id}/export")
async def export_profile(
    profile_id: str, user: Annotated[tuple[str, str], Depends(auth)]
) -> dict:
    _, token = user
    response = await rest(
        "GET",
        "speaker_profiles",
        token,
        params={
            "id": f"eq.{profile_id}",
            "select": "id,display_name,created_at,"
            "speaker_embeddings(id,embedding,source,created_at),"
            "consent_records(consented_by,consent_text_version,consented_at,revoked_at)",
        },
    )
    rows = response.json() if response.status_code == 200 else []
    if not rows:
        raise HTTPException(404, "Profile not found.")
    return rows[0]
