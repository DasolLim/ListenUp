"""Tests are hermetic: always mock services, regardless of the root .env
(app.main loads it at import, and a developer's .env may say `real`)."""

import os

os.environ["TRANSCRIPTION_SERVICE"] = "mock"
os.environ["SPEAKER_ID_SERVICE"] = "mock"
os.environ["TRANSLATION_SERVICE"] = "mock"
os.environ["ENHANCED_TRANSLATION_SERVICE"] = "mock"
os.environ["GENZ_EXPLAINER_SERVICE"] = "mock"
os.environ["TEXT_EMBEDDER"] = "hashing"
os.environ["TTS_SERVICE"] = "browser"  # free tier; never call a paid voice API in tests
os.environ.pop("MOCK_FIXTURE", None)
