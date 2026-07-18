"""Real OpenRouter client. Model via OPENROUTER_MODEL (env-swappable)."""

import json
import logging
import os

import httpx

from services.openrouter.base import (
    EnhancedTranslation,
    EnhancedTranslationService,
    SlangNote,
    coerce_enhanced,
    parse_llm_json,
)
from services.translate.base import SUPPORTED_LANGUAGES, assert_supported
from services.translate.cache import cache_key, get_cache

logger = logging.getLogger("listenup.openrouter")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

SYSTEM_PROMPT = """You are a cultural translation engine for an accessibility app.
Translate the user's text to {target_name} and explain slang/idioms.
Respond with ONLY a JSON object, no prose, no code fences:
{{"translation": "<text translated to {target_name}>",
 "register": "<one of: formal | neutral | casual | slang-heavy>",
 "slang_notes": [{{"phrase": "<original phrase>", "meaning": "<plain meaning>",
   "cultural_context": "<who says this, when>",
   "equivalent": "<closest {target_name} equivalent>"}}]}}
Include a slang_notes entry ONLY for genuine slang, idioms, or cultural references.
Empty list if none."""


class OpenRouterTranslationService(EnhancedTranslationService):
    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    async def _complete(self, text: str, target_lang: str, strict_nudge: bool) -> tuple[str, int]:
        target_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        system = SYSTEM_PROMPT.format(target_name=target_name)
        if strict_nudge:
            system += "\nYour previous output was invalid. Return ONLY valid JSON this time."
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "HTTP-Referer": "https://listenup.app",
                    "X-Title": "ListenUp",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
            )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        tokens = int((body.get("usage") or {}).get("total_tokens") or 0)
        return content, tokens

    async def translate(self, text: str, target_lang: str) -> EnhancedTranslation | None:
        assert_supported(target_lang)
        cache = get_cache()
        key = cache_key("llm", text, target_lang, self.model)
        if (hit := await cache.get(key)) is not None:
            return EnhancedTranslation(
                translation=hit["translation"],
                register=hit["register"],
                slang_notes=[SlangNote(**n) for n in hit["slang_notes"]],
                cached=True,
                model=self.model,
            )

        # One retry with a strictness nudge — LLM JSON is never trusted blindly.
        for attempt, nudge in enumerate((False, True)):
            try:
                content, tokens = await self._complete(text, target_lang, nudge)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
                logger.warning("openrouter_request_failed attempt=%d error=%s", attempt, exc)
                continue
            parsed = parse_llm_json(content)
            if parsed is None:
                logger.warning("openrouter_bad_json attempt=%d head=%r", attempt, content[:80])
                continue
            result = coerce_enhanced(parsed, self.model, tokens)
            if result is not None:
                await cache.set(
                    key,
                    {
                        "translation": result.translation,
                        "register": result.register,
                        "slang_notes": [n.__dict__ for n in result.slang_notes],
                    },
                )
                logger.info(
                    "openrouter_ok model=%s tokens=%d notes=%d",
                    self.model, tokens, len(result.slang_notes),
                )
                return result
        logger.warning("openrouter_gave_up text_len=%d", len(text))
        return None  # caller keeps the fast Google translation
