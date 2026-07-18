"""Tests are hermetic: always mock services, regardless of the root .env
(app.main loads it at import, and a developer's .env may say `real`)."""

import os

os.environ["TRANSCRIPTION_SERVICE"] = "mock"
os.environ["SPEAKER_ID_SERVICE"] = "mock"
os.environ.pop("MOCK_FIXTURE", None)
