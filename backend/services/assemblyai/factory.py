import os

from services.assemblyai.base import TranscriptionService


def get_transcription_service() -> TranscriptionService:
    """Mock by default (INTRODUCTION §6 cost awareness); real only when asked."""
    kind = os.environ.get("TRANSCRIPTION_SERVICE", "mock").lower()
    if kind == "real":
        from services.assemblyai.real import RealAssemblyAIService

        return RealAssemblyAIService()
    from services.assemblyai.mock import MockTranscriptionService

    return MockTranscriptionService()
