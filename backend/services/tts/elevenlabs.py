"""ElevenLabs TTS — premium presets plus consent-gated voice cloning.

Chosen over Google Cloud TTS / OpenAI TTS for two reasons: it covers Korean
well, and it is the only major provider whose cloning API is built around
verified consent from the voice owner, which is what makes the custom-voice
feature lawful here rather than an impersonation tool.

Opt-in: set `TTS_SERVICE=elevenlabs` and `ELEVENLABS_API_KEY`. Without those the
factory serves browser voices, so dev and CI never spend credits
(INTRODUCTION §6).

Audio is cached by (text, voice) so replaying the same translated line is free —
the same discipline as the translation cache.
"""

import logging
import os

import httpx

from services.translate.cache import cache_key, get_cache
from services.tts.base import (
    MAX_CLONE_SECONDS,
    MIN_CLONE_SECONDS,
    Speech,
    TtsError,
    TtsService,
    Voice,
    assert_speakable,
)

logger = logging.getLogger("listenup.tts.elevenlabs")

API_BASE = "https://api.elevenlabs.io/v1"
# Multilingual v2 handles English and Korean from one voice, so a cloned voice
# can speak both — the point of a translator that sounds like one person.
MODEL_ID = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
OUTPUT_MIME = "audio/mpeg"
REQUEST_TIMEOUT = 30.0

# Stock voices, stable IDs from the ElevenLabs public library. Multilingual, so
# each is offered for both supported languages.
PRESETS: tuple[tuple[str, str, str], ...] = (
    ("EXAVITQu4vr4xnSDxMaL", "Sarah — warm, natural (female)", "female"),
    ("TX3LPaxmHKxFdv7VOQHJ", "Liam — clear, steady (male)", "male"),
    ("XrExE9yKIg1WjnnlVkGX", "Matilda — bright, friendly (female)", "female"),
)


class ElevenLabsTtsService(TtsService):
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        if not self._api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set — unset TTS_SERVICE to use free browser voices"
            )

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key}

    async def voices(self, language: str | None = None) -> list[Voice]:
        if language is not None:
            assert_speakable(language)
        languages = [language] if language else ["en", "ko"]
        out: list[Voice] = []
        for lang in languages:
            for voice_id, label, gender in PRESETS:
                out.append(
                    Voice(
                        id=voice_id,
                        label=label,
                        language=lang,
                        gender=gender,
                        provider="cloud",
                    )
                )
        return out

    async def speak(self, text: str, voice_id: str) -> Speech:
        clean = text.strip()
        if not clean:
            raise TtsError("Nothing to speak.")

        cache = get_cache()
        key = cache_key("tts", clean, voice_id, MODEL_ID)
        if (hit := await cache.get(key)) is not None:
            # Cached as latin-1 text because the cache stores JSON strings.
            return Speech(
                voice_id=voice_id,
                audio=hit["audio"].encode("latin-1"),
                mime_type=hit["mime_type"],
                characters=0,
                cached=True,
            )

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    f"{API_BASE}/text-to-speech/{voice_id}",
                    headers={**self._headers(), "Content-Type": "application/json"},
                    json={
                        "text": clean,
                        "model_id": MODEL_ID,
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                    },
                )
                response.raise_for_status()
                audio = response.content
        except httpx.HTTPError as exc:
            # Never block the conversation on TTS: the caption is already on
            # screen, so the caller falls back to a browser voice.
            logger.warning("tts_synthesis_failed voice=%s error=%s", voice_id, exc)
            raise TtsError("Couldn't speak that just now. The text is still shown above.") from exc

        await cache.set(key, {"audio": audio.decode("latin-1"), "mime_type": OUTPUT_MIME})
        logger.info("tts_spoken voice=%s chars=%d bytes=%d", voice_id, len(clean), len(audio))
        return Speech(
            voice_id=voice_id,
            audio=audio,
            mime_type=OUTPUT_MIME,
            characters=len(clean),
        )

    async def clone_voice(self, name: str, sample: bytes, seconds: float) -> str:
        """Create a custom voice from a consented recording. Returns its id.

        The caller MUST have recorded consent from the person being cloned
        before calling this (see app/routes/tts.py). This method only enforces
        sample quality; consent is enforced at the route, where it is persisted.
        """
        if seconds < MIN_CLONE_SECONDS:
            raise TtsError(
                f"Need at least {int(MIN_CLONE_SECONDS)}s of clear speech to build a voice "
                f"(got {int(seconds)}s). Ask them to read a little more."
            )
        if seconds > MAX_CLONE_SECONDS:
            raise TtsError(f"Recording is too long — keep it under {int(MAX_CLONE_SECONDS)}s.")

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{API_BASE}/voices/add",
                    headers=self._headers(),
                    data={
                        "name": name,
                        # Recorded consent is held in our own consent_records
                        # table; this label makes the provider-side copy
                        # auditable too.
                        "labels": '{"source":"listenup","consent":"recorded"}',
                    },
                    files={"files": (f"{name}.wav", sample, "audio/wav")},
                )
                response.raise_for_status()
                voice_id = response.json().get("voice_id")
        except httpx.HTTPError as exc:
            logger.warning("tts_clone_failed name=%r error=%s", name, exc)
            raise TtsError("Couldn't build that voice right now. Try again in a moment.") from exc

        if not voice_id:
            raise TtsError("The voice provider didn't return a voice id.")
        logger.info("tts_voice_cloned name=%r voice=%s seconds=%.1f", name, voice_id, seconds)
        return str(voice_id)

    async def delete_voice(self, voice_id: str) -> None:
        """Remove a cloned voice from the provider (GDPR/BIPA deletion path)."""
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.delete(
                    f"{API_BASE}/voices/{voice_id}", headers=self._headers()
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("tts_delete_failed voice=%s error=%s", voice_id, exc)
            raise TtsError("Couldn't delete that voice from the provider. Try again.") from exc
        logger.info("tts_voice_deleted voice=%s", voice_id)
