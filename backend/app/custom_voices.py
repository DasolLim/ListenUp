"""A user's cloned voices — our rows and the provider's voices, kept in step.

Cloned voices are biometric data, so the Phase 3 enrolment rules apply
(INTRODUCTION §6) and they are enforced here rather than in the UI:

  - no consent from the person being recorded → nothing is created, and nothing
    reaches the provider;
  - a row that fails to save deletes the provider-side voice, because a clone
    with nothing here pointing at it is a biometric copy of someone that the
    person it belongs to cannot ask us to remove;
  - a provider that refuses deletion keeps our row, because that row is the only
    handle to a voice that still exists.

All of it used to be inline in the HTTP handler, which made every rule reachable
only through a request — and made the consent gate one `if` in a function, which
the next person adding a create path would have had to remember to copy.

`HTTPException` is raised directly, as `app.supa` does: this is an app-layer
module whose refusals are already phrased for a user, and translating them twice
would only give the two copies a chance to disagree.
"""

import logging

from fastapi import HTTPException

from app.supa import rest
from services.speaker_id.base import audio_seconds
from services.tts.base import VOICE_CLONE_CONSENT_VERSION, TtsError, Voice
from services.tts.library import VoiceLibrary

logger = logging.getLogger("listenup.tts.custom_voices")

# A person can hold a handful of cloned voices; this is a product cap, not a
# provider limit, and it keeps the picker readable.
MAX_CUSTOM_VOICES = 4

SELECT_ROW = "id,display_name,provider_voice_id,language,created_at"


class CustomVoiceStore:
    """One account's cloned voices."""

    def __init__(self, token: str, user_id: str, library: VoiceLibrary) -> None:
        self._token = token
        self._user_id = user_id
        self._library = library

    # ── Reading ──────────────────────────────────────────────────────────────

    async def rows(self, select: str = SELECT_ROW) -> list[dict]:
        """The stored rows, or a refusal that says which one it is."""
        response = await rest(
            "GET", "custom_voices", self._token, params={"select": select}
        )
        if response.status_code == 200:
            rows: list[dict] = response.json()  # trusted boundary: PostgREST
            return rows
        body = response.text or ""
        # A missing migration is the likeliest cause and used to surface as a
        # generic 502, sending people hunting through server logs. PostgREST
        # reports PGRST205 when the table isn't in the schema cache.
        if "PGRST205" in body or (response.status_code == 404 and "custom_voices" in body):
            raise HTTPException(
                503,
                "Custom voices aren't set up on this deployment yet: the "
                "custom_voices table is missing. Preset voices still work.",
            )
        raise HTTPException(502, "Could not load your custom voices.")

    async def voices(self, language: str | None = None) -> list[Voice]:
        """The account's voices, shaped like any preset, for a picker.

        Never raises. Live captions and translation both depend on the voice
        list, so a missing table or an expired token should cost you your own
        voices, not the ability to speak at all.
        """
        try:
            rows = await self.rows("display_name,provider_voice_id,language")
        except Exception:
            logger.warning("custom_voice_list_failed", exc_info=True)
            return []
        return [
            _as_voice(row)
            for row in rows
            if language is None or row.get("language") == language
        ]

    # ── Creating ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        display_name: str,
        sample: bytes,
        language: str,
        consent_given: bool,
        consented_by: str,
    ) -> dict:
        """Clone a voice from a recording — only with the speaker's consent.

        The consent gate is deliberately first, before the cap and before the
        provider is touched: being over a cap is a product limit, but recording
        someone without their agreement is impersonation.
        """
        name = display_name.strip()
        signer = consented_by.strip()
        if not consent_given or not signer:
            raise HTTPException(
                400,
                "Consent is required: the person being recorded must agree before "
                "ListenUp can build a voice from their speech. Their voice is "
                "biometric data.",
            )

        existing = await self.rows("id")
        if len(existing) >= MAX_CUSTOM_VOICES:
            raise HTTPException(
                400,
                f"You already have {MAX_CUSTOM_VOICES} custom voices. "
                "Delete one to add another.",
            )

        try:
            provider_voice_id = await self._library.clone(
                name, sample, audio_seconds(sample)
            )
        except TtsError as exc:
            raise HTTPException(400, str(exc)) from exc

        insert = await rest(
            "POST",
            "custom_voices",
            self._token,
            json={
                "owner_user_id": self._user_id,
                "display_name": name,
                "provider_voice_id": provider_voice_id,
                "language": language,
                "consented_by": signer,
                "consent_text_version": VOICE_CLONE_CONSENT_VERSION,
            },
        )
        if insert.status_code not in (200, 201):
            await self._discard(provider_voice_id)
            raise HTTPException(502, "Could not save that voice. Nothing was kept.")

        logger.info(
            "tts_custom_voice_created name=%r seconds=%.1f consent_version=%s",
            name, audio_seconds(sample), VOICE_CLONE_CONSENT_VERSION,
        )
        return {"display_name": name, "language": language}

    async def _discard(self, provider_voice_id: str) -> None:
        """Don't leave an orphan at the provider if our row failed to save."""
        try:
            await self._library.forget(provider_voice_id)
        except TtsError:
            logger.warning("tts_orphan_voice provider_voice=%s", provider_voice_id)

    # ── Deleting ─────────────────────────────────────────────────────────────

    async def delete(self, voice_id: str) -> None:
        """Remove a cloned voice from the provider and from our records."""
        lookup = await rest(
            "GET",
            "custom_voices",
            self._token,
            params={"id": f"eq.{voice_id}", "select": "provider_voice_id"},
        )
        rows = lookup.json() if lookup.status_code == 200 else []
        if not rows:
            raise HTTPException(404, "That voice no longer exists.")

        try:
            await self._library.forget(rows[0]["provider_voice_id"])
        except TtsError as exc:
            # Our row stays so the user can retry rather than losing the handle
            # to a voice that still exists at the provider.
            raise HTTPException(502, str(exc)) from exc

        removed = await rest(
            "DELETE", "custom_voices", self._token, params={"id": f"eq.{voice_id}"}
        )
        if removed.status_code not in (200, 204):
            raise HTTPException(502, "Could not delete that voice. Try again.")
        logger.info("tts_custom_voice_deleted voice=%s", voice_id)


def _as_voice(row: dict) -> Voice:
    """Adapt a stored custom voice into the same shape as a preset."""
    return Voice(
        id=row["provider_voice_id"],
        label=f"{row['display_name']} (custom)",
        language=row.get("language", "en"),
        gender="neutral",
        provider="custom",
        owner_name=row["display_name"],
    )
