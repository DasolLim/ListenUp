"""Mock cultural translator: canned register + slang notes, zero cost."""

from services.openrouter.base import (
    EnhancedTranslation,
    EnhancedTranslationService,
    SlangNote,
)
from services.translate.base import assert_supported
from services.translate.cache import cache_key, get_cache

_KNOWN_SLANG: dict[str, SlangNote] = {
    "no cap": SlangNote(
        phrase="no cap",
        meaning="no lie; I'm being completely honest",
        cultural_context="Gen Z internet slang, from hip-hop; 'cap' means a lie",
        equivalent="de verdad",
    ),
    "spill the tea": SlangNote(
        phrase="spill the tea",
        meaning="share the gossip",
        cultural_context="drag/ballroom culture via Black Twitter",
        equivalent="cuenta el chisme",
    ),
    "goat": SlangNote(
        phrase="GOAT",
        meaning="Greatest Of All Time",
        cultural_context="sports fandom acronym",
        equivalent="el mejor de la historia",
    ),
}


class MockEnhancedTranslationService(EnhancedTranslationService):
    async def translate(self, text: str, target_lang: str) -> EnhancedTranslation | None:
        assert_supported(target_lang)
        cache = get_cache()
        key = cache_key("llm", text, target_lang, "mock")
        if (hit := await cache.get(key)) is not None:
            return EnhancedTranslation(
                translation=hit["translation"],
                register=hit["register"],
                slang_notes=[SlangNote(**n) for n in hit["slang_notes"]],
                cached=True,
                model="mock",
            )
        lowered = text.lower()
        notes = [note for phrase, note in _KNOWN_SLANG.items() if phrase in lowered]
        result = EnhancedTranslation(
            translation=f"[{target_lang}+] {text}",
            register="slang-heavy" if notes else "casual",
            slang_notes=notes,
            model="mock",
            tokens=len(text.split()) * 3,
        )
        await cache.set(
            key,
            {
                "translation": result.translation,
                "register": result.register,
                "slang_notes": [n.__dict__ for n in result.slang_notes],
            },
        )
        return result
