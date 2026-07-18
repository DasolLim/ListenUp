import os
from functools import lru_cache

from services.translate.base import TranslationService


@lru_cache(maxsize=1)
def get_translation_service() -> TranslationService:
    kind = os.environ.get("TRANSLATION_SERVICE", "mock").lower()
    if kind == "real":
        from services.translate.google import GoogleTranslationService

        return GoogleTranslationService()
    from services.translate.mock import MockTranslationService

    return MockTranslationService()
