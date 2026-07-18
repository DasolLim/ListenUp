import os
from functools import lru_cache

from services.openrouter.base import EnhancedTranslationService


@lru_cache(maxsize=1)
def get_enhanced_translation_service() -> EnhancedTranslationService:
    kind = os.environ.get("ENHANCED_TRANSLATION_SERVICE", "mock").lower()
    if kind == "real":
        from services.openrouter.real import OpenRouterTranslationService

        return OpenRouterTranslationService()
    from services.openrouter.mock import MockEnhancedTranslationService

    return MockEnhancedTranslationService()
