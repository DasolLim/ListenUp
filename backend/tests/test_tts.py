"""Text-to-speech: voice listing, synthesis, and the voice-cloning consent gate.

The consent tests matter most. A cloned voice can say words the person never
said, so "no consent → nothing is created" is a product rule, not a UI nicety,
and it is asserted here at the API boundary.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from services.tts.base import (
    MAX_CLONE_SECONDS,
    MIN_CLONE_SECONDS,
    TtsError,
    assert_speakable,
)
from services.tts.browser import BrowserTtsService

client = TestClient(app)


# ── Voice catalogue ───────────────────────────────────────────────────────────

def test_voices_endpoint_offers_male_and_female_per_language():
    body = client.get("/tts/voices").json()
    voices = body["voices"]
    for language in ("en", "ko"):
        genders = {v["gender"] for v in voices if v["language"] == language}
        assert "female" in genders, f"no female voice for {language}"
        assert "male" in genders, f"no male voice for {language}"


def test_voices_can_be_filtered_by_language():
    body = client.get("/tts/voices", params={"language": "ko"}).json()
    assert body["voices"]
    assert {v["language"] for v in body["voices"]} == {"ko"}


def test_voices_endpoint_publishes_the_consent_copy():
    """The clone UI must show consent text; it comes from the API so the stored
    version and the displayed wording can never drift apart."""
    body = client.get("/tts/voices").json()
    assert body["consent_version"]
    assert "biometric" in body["consent_text"].lower()


def test_unsupported_language_is_rejected():
    response = client.get("/tts/voices", params={"language": "fr"})
    assert response.status_code == 400
    assert "fr" in response.json()["detail"]


def test_assert_speakable_matches_translation_scope():
    assert_speakable("en")
    assert_speakable("ko")
    with pytest.raises(TtsError):
        assert_speakable("ja")


# ── Synthesis ─────────────────────────────────────────────────────────────────

def test_speak_returns_local_instruction_on_the_free_tier():
    """Browser voices cost nothing: the server sends no audio, the client speaks."""
    response = client.post(
        "/tts/speak", json={"text": "Are you coming Sunday?", "voice_id": "browser-en-female"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["speak_locally"] is True
    assert body["audio_base64"] == ""
    assert body["characters"] == len("Are you coming Sunday?")


def test_speak_handles_korean_text():
    response = client.post(
        "/tts/speak", json={"text": "저녁 준비는 제가 할게요.", "voice_id": "browser-ko-male"}
    )
    assert response.status_code == 200
    assert response.json()["speak_locally"] is True


def test_speak_rejects_empty_text():
    response = client.post("/tts/speak", json={"text": "", "voice_id": "browser-en-female"})
    assert response.status_code == 422


def test_browser_service_never_returns_audio():
    service = BrowserTtsService()
    result = asyncio.run(service.speak("hello", "browser-en-female"))
    assert result.audio == b""
    assert result.speak_locally is True


# ── Consent gate (the rule that matters) ──────────────────────────────────────

def _clone_form(**overrides) -> dict:
    form = {
        "display_name": "Mom",
        "consent_given": "true",
        "consented_by": "Mom",
        "language": "en",
    }
    form.update(overrides)
    return form


def test_cloning_requires_authentication():
    response = client.post(
        "/tts/custom-voices",
        data=_clone_form(),
        files={"sample": ("v.wav", b"\x00" * 32000, "audio/wav")},
    )
    assert response.status_code == 401


def test_cloning_without_consent_is_refused(monkeypatch):
    """Even with a valid session, no consent means nothing is created."""
    monkeypatch.setattr("app.routes.tts.verify_user", _fake_verify)
    response = client.post(
        "/tts/custom-voices",
        headers={"Authorization": "Bearer test-token"},
        data=_clone_form(consent_given="false"),
        files={"sample": ("v.wav", b"\x00" * 32000, "audio/wav")},
    )
    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()


def test_cloning_without_a_named_consenting_person_is_refused(monkeypatch):
    monkeypatch.setattr("app.routes.tts.verify_user", _fake_verify)
    response = client.post(
        "/tts/custom-voices",
        headers={"Authorization": "Bearer test-token"},
        data=_clone_form(consented_by="   "),
        files={"sample": ("v.wav", b"\x00" * 32000, "audio/wav")},
    )
    assert response.status_code == 400
    assert "consent" in response.json()["detail"].lower()


def test_cloning_on_the_free_tier_explains_itself(monkeypatch):
    """Browser voices can't clone. The error must say what to do, and must not
    pretend the voice was created."""
    monkeypatch.setattr("app.routes.tts.verify_user", _fake_verify)
    monkeypatch.setattr("app.routes.tts.rest", _fake_rest_empty)
    response = client.post(
        "/tts/custom-voices",
        headers={"Authorization": "Bearer test-token"},
        data=_clone_form(),
        files={"sample": ("v.wav", b"\x00" * 32000, "audio/wav")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "cloud voice provider" in detail
    assert "preset voices keep working" in detail


def test_clone_sample_length_bounds_are_sane():
    """A too-short sample produces a voice that sounds like nobody, so the
    minimum is enforced rather than silently accepted."""
    assert MIN_CLONE_SECONDS >= 10.0
    assert MAX_CLONE_SECONDS > MIN_CLONE_SECONDS


# ── Test doubles ──────────────────────────────────────────────────────────────

async def _fake_verify(_token: str) -> str:
    return "11111111-1111-1111-1111-111111111111"


class _Response:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


async def _fake_rest(_method, _table, _token, **_kwargs):
    return _Response(200, [])


_fake_rest_empty = _fake_rest
