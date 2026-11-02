"""Text-to-speech QA: the voice catalogue, custom voices, and cost behaviour.

Complements test_tts.py (which covers the API contract) with the guarantees a
user would notice if they broke: the promised voices exist, a deleted voice
cannot silently become a different voice, and the free tier never bills.
"""

import asyncio

from fastapi.testclient import TestClient

from app.main import app
from services.tts import get_tts_service
from services.tts.browser import BROWSER_VOICES, BrowserTtsService

client = TestClient(app)

# The three voices the product promises per language.
EXPECTED_GENDERS = {"female", "male", "neutral"}


def test_every_supported_language_has_all_three_voice_kinds():
    """The UI offers Aria / Miles / System default. If a language loses one, the
    picker silently shrinks."""
    for language in ("en", "ko"):
        genders = {v.gender for v in BROWSER_VOICES if v.language == language}
        assert genders == EXPECTED_GENDERS, f"{language} has {genders}"


def test_voice_ids_are_unique():
    """Duplicate ids would make the picker ambiguous and break per-voice shape
    storage, which is keyed on the id."""
    ids = [v.id for v in BROWSER_VOICES]
    assert len(ids) == len(set(ids))


def test_every_voice_has_a_human_label():
    for voice in BROWSER_VOICES:
        assert voice.label.strip(), f"{voice.id} has no label"
        assert voice.id not in voice.label, "labels must be human, not ids"


def test_hints_cover_macos_windows_and_android():
    """A hint list that only names macOS voices leaves Windows and Android
    falling through to the platform default, which for Korean can mean an
    English voice reading Hangul. Each hinted voice must name at least one
    Microsoft (Windows/SAPI) and one Google/Android candidate."""
    hinted = [v for v in BROWSER_VOICES if v.browser_hint]
    assert hinted, "no voices carry hints"
    for voice in hinted:
        hint = voice.browser_hint.lower()
        assert "microsoft" in hint, f"{voice.id} has no Windows candidate"
        assert "google" in hint or "-x-" in hint, f"{voice.id} has no Google/Android candidate"


def test_hint_lists_are_pipe_separated_and_clean():
    """The client splits on '|'. Stray empty segments would match everything."""
    for voice in BROWSER_VOICES:
        if not voice.browser_hint:
            continue
        parts = voice.browser_hint.split("|")
        assert all(p.strip() for p in parts), f"{voice.id} has an empty hint segment"
        assert len(parts) == len(set(parts)), f"{voice.id} repeats a hint"


def test_korean_voices_carry_korean_hints():
    """browser_hint drives OS voice matching. A Korean voice with only English
    hints would fall back to an English speaker reading Hangul."""
    korean = [v for v in BROWSER_VOICES if v.language == "ko" and v.browser_hint]
    assert korean, "no Korean voices carry hints"
    for voice in korean:
        assert voice.browser_hint, f"{voice.id} has no hint"


def test_free_tier_never_reports_billable_audio():
    """Browser voices are rendered by the user's device. Any server-side audio
    here would mean we started paying for the default tier."""
    service = get_tts_service()
    for voice in BROWSER_VOICES:
        result = asyncio.run(service.speak("test", voice.id))
        assert result.audio == b""
        assert result.speak_locally is True


def test_speaking_an_unknown_voice_fails_loudly():
    """Regression: a stale or deleted custom-voice id used to fall back to a
    default voice, so the app would speak as a stranger with no explanation."""
    response = client.post("/tts/speak", json={"text": "hi", "voice_id": "removed-voice"})
    assert response.status_code == 503
    assert "unknown voice" in response.json()["detail"].lower()


def test_voices_endpoint_matches_the_service_catalogue():
    """The API and the service must not drift; the UI trusts the API."""
    body = client.get("/tts/voices").json()
    assert {v["id"] for v in body["voices"]} == {v.id for v in BROWSER_VOICES}


def test_language_filter_never_leaks_another_language():
    for language in ("en", "ko"):
        body = client.get("/tts/voices", params={"language": language}).json()
        assert {v["language"] for v in body["voices"]} == {language}


def test_custom_voice_endpoints_require_a_session():
    """Custom voices are biometric data; they are never world-readable."""
    assert client.get("/tts/custom-voices").status_code == 401
    assert client.delete("/tts/custom-voices/some-id").status_code == 401


def test_consent_copy_names_the_obligations():
    """The consent statement must actually say what the user is agreeing to, or
    it is not informed consent."""
    body = client.get("/tts/voices").json()
    text = body["consent_text"].lower()
    for phrase in ("voice", "biometric", "delet"):
        assert phrase in text, f"consent text never mentions {phrase!r}"


def test_missing_table_says_so_instead_of_a_generic_502(monkeypatch):
    """Regression: before migration 0003 was applied, listing custom voices
    returned a bare 502, so the real cause (a missing table) was invisible.
    Postgrest reports PGRST205 when the table isn't in the schema cache."""

    class _Missing:
        status_code = 404
        text = '{"code":"PGRST205","message":"Could not find the table '\
               '\'public.custom_voices\' in the schema cache"}'

        def json(self):
            return {}

    async def _fake_verify(_token: str) -> str:
        return "11111111-1111-1111-1111-111111111111"

    async def _fake_rest(*_a, **_k):
        return _Missing()

    monkeypatch.setattr("app.routes.tts.verify_user", _fake_verify)
    monkeypatch.setattr("app.custom_voices.rest", _fake_rest)

    response = client.get("/tts/custom-voices", headers={"Authorization": "Bearer t"})
    assert response.status_code == 503
    detail = response.json()["detail"].lower()
    assert "custom_voices table is missing" in detail
    assert "preset voices still work" in detail


def test_browser_service_reports_characters_for_the_cost_audit():
    service = BrowserTtsService()
    result = asyncio.run(service.speak("hello there", "browser-en-female"))
    assert result.characters == len("hello there")
