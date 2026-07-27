import os
from functools import lru_cache

from services.tts.base import TtsService


@lru_cache(maxsize=1)
def get_tts_service() -> TtsService:
    """Browser voices by default (free, no key). `TTS_SERVICE=elevenlabs` opts
    into cloud synthesis and custom voices."""
    kind = os.environ.get("TTS_SERVICE", "browser").lower()
    if kind == "elevenlabs":
        from services.tts.elevenlabs import ElevenLabsTtsService

        return ElevenLabsTtsService()
    from services.tts.browser import BrowserTtsService

    return BrowserTtsService()
