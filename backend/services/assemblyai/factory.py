import os

from services.assemblyai.base import STREAMING_LANGUAGES, TranscriptionService


def get_transcription_service(language: str = "en") -> TranscriptionService:
    """Mock by default (INTRODUCTION §6 cost awareness); real only when asked.

    Language picks the transport: AssemblyAI can stream English, but has no
    streaming model for Korean, so Korean goes through the same provider's async
    (batch) endpoint — higher latency, same interface.
    """
    kind = os.environ.get("TRANSCRIPTION_SERVICE", "mock").lower()
    if kind == "real":
        if language in STREAMING_LANGUAGES:
            from services.assemblyai.real import RealAssemblyAIService

            return RealAssemblyAIService()
        from services.assemblyai.batch import BatchAssemblyAIService

        return BatchAssemblyAIService()
    from services.assemblyai.mock import MockTranscriptionService

    return MockTranscriptionService()
