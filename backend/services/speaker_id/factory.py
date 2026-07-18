import os
from functools import lru_cache

from services.speaker_id.base import SpeakerEmbedder


@lru_cache(maxsize=1)
def get_speaker_embedder() -> SpeakerEmbedder:
    """Singleton — the model must load once at startup, never per request."""
    kind = os.environ.get("SPEAKER_ID_SERVICE", "mock").lower()
    if kind == "real":
        from services.speaker_id.real import EcapaSpeakerEmbedder

        return EcapaSpeakerEmbedder()
    from services.speaker_id.mock import MockSpeakerEmbedder

    return MockSpeakerEmbedder()
