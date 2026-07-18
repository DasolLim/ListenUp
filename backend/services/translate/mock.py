"""Mock translation: deterministic, zero-cost, cache-identical behavior.

Marks output visibly (`[ko]` prefix) and "detects" a handful of languages by
common words so the mixed-language live gate can run without API spend.
"""

from services.translate.base import (
    TranslationResult,
    TranslationService,
    assert_supported,
)
from services.translate.cache import cache_key, get_cache

_DETECT_HINTS: list[tuple[str, str]] = [
    ("es", "hola|gracias|buenos|cómo|qué"),
    ("fr", "bonjour|merci|comment|c'est"),
    ("ko", "안녕|감사|저녁|우리"),
    ("ja", "こんにちは|ありがとう"),
    ("de", "hallo|danke|wie geht"),
]


def _detect(text: str) -> str:
    lowered = text.lower()
    for lang, hints in _DETECT_HINTS:
        if any(hint in lowered for hint in hints.split("|")):
            return lang
    return "en"


class MockTranslationService(TranslationService):
    async def translate(
        self, text: str, target_lang: str, source_lang: str | None = None
    ) -> TranslationResult:
        assert_supported(target_lang)
        cache = get_cache()
        key = cache_key("g", text, target_lang)
        if (hit := await cache.get(key)) is not None:
            return TranslationResult(hit["text"], hit.get("source"), cached=True)
        detected = source_lang or _detect(text)
        translated = text if detected == target_lang else f"[{target_lang}] {text}"
        await cache.set(key, {"text": translated, "source": detected})
        return TranslationResult(translated, detected, characters=len(text))
