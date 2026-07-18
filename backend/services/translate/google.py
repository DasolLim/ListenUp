"""Real Google Cloud Translation v3 (translateText), authed via ADC.

Local dev: `gcloud auth application-default login` (org policy blocks
service-account keys — see CLAUDE.md 2026-07-17). Tokens are refreshed and
cached; calls go through httpx, no heavy client library.
"""

import asyncio
import logging
import os
from typing import Any

import httpx

from services.translate.base import (
    TranslationError,
    TranslationResult,
    TranslationService,
    assert_supported,
)
from services.translate.cache import cache_key, get_cache

logger = logging.getLogger("listenup.translate")


class GoogleTranslationService(TranslationService):
    def __init__(self) -> None:
        self._project = os.environ.get("GOOGLE_CLOUD_PROJECT_ID", "")
        if not self._project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID is not set")
        self._credentials: Any = None

    def _token(self) -> str:
        """Blocking ADC refresh — call via to_thread."""
        import google.auth
        import google.auth.transport.requests

        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        if not self._credentials.valid:
            self._credentials.refresh(google.auth.transport.requests.Request())
        return str(self._credentials.token)

    async def translate(
        self, text: str, target_lang: str, source_lang: str | None = None
    ) -> TranslationResult:
        assert_supported(target_lang)
        cache = get_cache()
        key = cache_key("g", text, target_lang)
        if (hit := await cache.get(key)) is not None:
            return TranslationResult(
                hit["text"], hit.get("source"), cached=True, characters=0
            )

        token = await asyncio.to_thread(self._token)
        body: dict = {
            "contents": [text],
            "targetLanguageCode": target_lang,
            "mimeType": "text/plain",
        }
        if source_lang:
            body["sourceLanguageCode"] = source_lang
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"https://translation.googleapis.com/v3/projects/{self._project}"
                "/locations/global:translateText",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-goog-user-project": self._project,
                },
                json=body,
            )
        if response.status_code != 200:
            logger.warning("google_translate_error status=%s", response.status_code)
            raise TranslationError(
                "Translation is temporarily unavailable. The original text is unchanged."
            )
        item = response.json()["translations"][0]
        result = TranslationResult(
            item["translatedText"],
            item.get("detectedLanguageCode") or source_lang,
            characters=len(text),
        )
        await cache.set(key, {"text": result.text, "source": result.detected_source_lang})
        logger.info(
            "google_translate chars=%d target=%s source=%s",
            len(text), target_lang, result.detected_source_lang,
        )
        return result
