"""Spoken-language routing: English streams, Korean falls back to the batch
path (AssemblyAI has no Korean streaming model), unsupported codes are rejected."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.assemblyai.base import (
    BATCH_LANGUAGES,
    STREAMING_LANGUAGES,
    UnsupportedLanguageError,
    assert_spoken_language,
)
from services.assemblyai.real import build_url

client = TestClient(app)


def test_languages_endpoint_reports_modes() -> None:
    body = client.get("/transcribe/languages").json()
    assert body["languages"] == {"en": "English", "ko": "Korean"}
    assert body["modes"]["en"] == "streaming"
    assert body["modes"]["ko"] == "batch"  # no streaming model exists for Korean


def test_assert_spoken_language() -> None:
    assert_spoken_language("en")
    assert_spoken_language("ko")
    with pytest.raises(UnsupportedLanguageError, match="Unsupported spoken language 'ja'"):
        assert_spoken_language("ja")


def test_korean_is_batch_english_is_streaming() -> None:
    assert "en" in STREAMING_LANGUAGES and "en" not in BATCH_LANGUAGES
    assert "ko" in BATCH_LANGUAGES and "ko" not in STREAMING_LANGUAGES


def test_english_url_carries_slang_keyterms_non_english_does_not() -> None:
    english = build_url(16000, language="en")
    assert "keyterms_prompt" in english
    assert "speaker_labels=true" in english
    # Keyterms are English slang — sending them with another language just biases
    # recognition toward the wrong vocabulary.
    assert "keyterms_prompt" not in build_url(16000, language="ko")


def test_ws_rejects_unsupported_spoken_language() -> None:
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text('{"sampleRate": 16000, "encoding": "pcm_s16le", "language": "ja"}')
        message = ws.receive_json()
        assert message["type"] == "error"
        assert "Unsupported spoken language 'ja'" in message["message"]


def test_ws_ready_announces_language_and_mode() -> None:
    with client.websocket_connect("/ws/transcribe") as ws:
        ws.send_text('{"sampleRate": 16000, "encoding": "pcm_s16le", "language": "ko"}')
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["language"] == "ko"
        assert ready["mode"] == "batch"
