"""General translation interface (INTRODUCTION §4: Google v3 = coverage/speed;
OpenRouter handles the cultural layer separately)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Launch scope: English and Korean only. We would rather do two languages
# excellently (register, slang, cultural nuance) than many shallowly. Google v3
# and OpenRouter both support far more, so widening later is only this list.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "ko": "Korean",
}


class TranslationError(Exception):
    """User-presentable translation failure (bad language, provider down)."""


@dataclass(frozen=True)
class TranslationResult:
    text: str
    detected_source_lang: str | None
    cached: bool = False
    characters: int = 0  # billed characters (cost audit, Phase 4.6)


def assert_supported(target_lang: str) -> None:
    if target_lang not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise TranslationError(
            f"Unsupported target language '{target_lang}'. Supported: {supported}."
        )


class TranslationService(ABC):
    @abstractmethod
    async def translate(
        self, text: str, target_lang: str, source_lang: str | None = None
    ) -> TranslationResult: ...
