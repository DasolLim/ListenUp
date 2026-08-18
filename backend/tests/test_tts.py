"""Text-to-speech: voice listing, synthesis, and the voice-cloning consent gate.

The consent tests matter most. A cloned voice can say words the person never
said, so "no consent → nothing is created" is a product rule, not a UI nicety,
and it is asserted here at the API boundary.
"""

import asyncio
from uuid import uuid4

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


def test_voices_offer_real_variety_per_gender_and_language():
    """Three of each gender per language, so picking a voice is a real choice.

    Asserted at the API because the catalogue is the contract the picker renders;
    dropping back to one voice each would silently shrink the feature.
    """
    body = client.get("/tts/voices").json()
    for language in ("en", "ko"):
        for gender in ("female", "male"):
            matching = [
                v for v in body["voices"] if v["language"] == language and v["gender"] == gender
            ]
            assert len(matching) >= 3, f"only {len(matching)} {gender} voice(s) for {language}"


def test_every_named_voice_has_distinct_hints_and_labels():
    """Two entries resolving to the same OS voice would make the picker lie.

    Identical labels or identical first-choice hints are the two ways that
    happens, so both are checked here rather than discovered by ear.
    """
    voices = client.get("/tts/voices").json()["voices"]
    labels = [v["label"] for v in voices]
    assert len(labels) == len(set(labels)), "duplicate voice label"

    for language in ("en", "ko"):
        named = [
            v for v in voices if v["language"] == language and v["browser_hint"]
        ]
        first_choices = [v["browser_hint"].split("|")[0] for v in named]
        assert len(first_choices) == len(set(first_choices)), (
            f"{language}: two voices claim the same first-choice OS voice"
        )


def test_every_voice_id_is_unique_and_speakable():
    """An id collision would make one voice unreachable through /tts/speak."""
    voices = client.get("/tts/voices").json()["voices"]
    ids = [v["id"] for v in voices]
    assert len(ids) == len(set(ids))
    for voice_id in ids:
        response = client.post("/tts/speak", json={"text": "hello", "voice_id": voice_id})
        assert response.status_code == 200, f"{voice_id} is listed but not speakable"


def test_each_language_keeps_a_system_default():
    """The no-hint entry is the fallback when a device has unusual voices."""
    voices = client.get("/tts/voices").json()["voices"]
    for language in ("en", "ko"):
        neutral = [
            v for v in voices if v["language"] == language and v["gender"] == "neutral"
        ]
        assert len(neutral) == 1
        assert neutral[0]["browser_hint"] == ""


def _patch_rest(patcher, double) -> None:
    """Install a PostgREST double on both seams that use one.

    The route reads `subscriptions` to resolve the plan; `app.custom_voices`
    reads and writes `custom_voices`. One table-dispatching double serves both,
    and patching both is what keeps a test from passing because it happened to
    stub the only call the code still made.
    """
    patcher.setattr("app.routes.tts.rest", double)
    patcher.setattr("app.custom_voices.rest", double)


def test_recorded_voices_reach_the_picker():
    """Regression: cloning used to be a dead end.

    A voice could be created, listed in the studio and deleted, but /tts/voices
    never queried custom_voices — so it never appeared in a picker and could
    never actually be spoken with. The whole feature was unreachable.
    """
    monkey = pytest.MonkeyPatch()
    _patch_rest(monkey, _fake_rest_one_voice)
    try:
        body = client.get("/tts/voices", headers={"Authorization": "Bearer test-token"}).json()
    finally:
        monkey.undo()
    custom = [v for v in body["voices"] if v["provider"] == "custom"]
    assert len(custom) == 1
    assert custom[0]["id"] == "el_voice_123"          # the provider handle to speak with
    assert "Mom" in custom[0]["label"]
    assert custom[0]["owner_name"] == "Mom"


def test_anonymous_callers_still_get_preset_voices():
    """The endpoint stays public: browser voices need no account."""
    body = client.get("/tts/voices").json()
    assert body["voices"]
    assert all(v["provider"] == "browser" for v in body["voices"])


def test_a_failed_custom_voice_lookup_does_not_break_the_preset_list():
    """Captions and translation both depend on this endpoint. A missing table or
    an expired token must cost you your own voices, not the ability to speak."""
    monkey = pytest.MonkeyPatch()
    _patch_rest(monkey, _fake_rest_exploding)
    try:
        response = client.get("/tts/voices", headers={"Authorization": "Bearer test-token"})
    finally:
        monkey.undo()
    assert response.status_code == 200
    assert response.json()["voices"], "preset voices disappeared when the lookup failed"


def test_recorded_voices_respect_the_language_filter():
    monkey = pytest.MonkeyPatch()
    _patch_rest(monkey, _fake_rest_one_voice)
    try:
        body = client.get(
            "/tts/voices", params={"language": "ko"}, headers={"Authorization": "Bearer t"}
        ).json()
    finally:
        monkey.undo()
    # The fixture voice is English, so a Korean picker must not offer it.
    assert not [v for v in body["voices"] if v["provider"] == "custom"]


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


def test_unknown_voice_id_is_rejected_not_silently_substituted():
    """Regression: an unknown id used to return 200 and speak in a default
    voice. A stale or deleted custom voice would then speak as a stranger with
    nothing to explain why."""
    response = client.post(
        "/tts/speak", json={"text": "hello", "voice_id": "deleted-custom-voice"}
    )
    assert response.status_code == 503
    assert "unknown voice" in response.json()["detail"].lower()


def test_expressiveness_is_accepted_and_ignored_by_the_free_tier():
    """The browser tier renders client-side, so it has nothing to apply
    expressiveness to — but sending it must not break the request, or a user who
    set the slider on a cloud voice could no longer speak with a browser one."""
    response = client.post(
        "/tts/speak",
        json={"text": "hello", "voice_id": "browser-en-female", "expressiveness": 0.9},
    )
    assert response.status_code == 200
    assert response.json()["speak_locally"] is True


def test_expressiveness_outside_zero_to_one_is_rejected():
    """Out-of-range values would be passed to the provider verbatim."""
    for bad in (-0.5, 1.5):
        response = client.post(
            "/tts/speak",
            json={"text": "hello", "voice_id": "browser-en-female", "expressiveness": bad},
        )
        assert response.status_code == 422, f"{bad} was accepted"


def test_expressiveness_maps_to_inverse_stability_and_varies_the_cache_key():
    """Two things at once, because they are the same bug if either is wrong:
    expressiveness must invert to `stability`, and it must be part of the cache
    key — otherwise the first setting rendered is replayed for every later one.
    """
    from services.tts.elevenlabs import ElevenLabsTtsService

    service = ElevenLabsTtsService(api_key="test-key")
    sent: list[dict] = []

    class _FakeResponse:
        content = b"audio-bytes"

        def raise_for_status(self):
            return None

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def post(self, _url, **kwargs):
            sent.append(kwargs["json"])
            return _FakeResponse()

    import httpx

    # The TTS cache is a process-wide singleton, so text used by another test
    # would be served from cache and never reach the fake client. A unique
    # phrase keeps this test independent of suite ordering.
    phrase = f"expressiveness probe {uuid4()}"

    original = httpx.AsyncClient
    httpx.AsyncClient = lambda **_kw: _FakeClient()  # type: ignore[assignment]
    try:
        asyncio.run(service.speak(phrase, "voice-1", expressiveness=1.0))
        asyncio.run(service.speak(phrase, "voice-1", expressiveness=0.0))
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]

    # Fully expressive → stability 0; fully flat → stability 1.
    assert sent[0]["voice_settings"]["stability"] == pytest.approx(0.0)
    # A second call with different expressiveness must reach the provider rather
    # than being served the first call's cached audio.
    assert len(sent) == 2, "the cache served different expressiveness from one key"
    assert sent[1]["voice_settings"]["stability"] == pytest.approx(1.0)


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


def test_cloning_is_refused_on_a_plan_that_does_not_include_it(monkeypatch):
    """Free and Basic don't clone. The refusal must name Pro rather than read as
    a malfunction."""
    monkeypatch.setattr("app.routes.tts.verify_user", _fake_verify)
    for tier in ("free", "basic"):
        _patch_rest(monkeypatch, _rest_on_plan(tier))
        response = client.post(
            "/tts/custom-voices",
            headers={"Authorization": "Bearer test-token"},
            data=_clone_form(),
            files={"sample": ("v.wav", b"\x00" * 32000, "audio/wav")},
        )
        assert response.status_code == 402, tier
        detail = response.json()["detail"]
        assert detail["upgradeTo"] == "pro", tier
        assert "pro" in detail["message"].lower(), tier


def test_cloning_on_pro_without_a_cloud_provider_explains_itself(monkeypatch):
    """The plan allows it but the deployment has no ElevenLabs key. The error
    must say what to do, and must not pretend the voice was created."""
    monkeypatch.setattr("app.routes.tts.verify_user", _fake_verify)
    _patch_rest(monkeypatch, _fake_rest_pro)
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


async def _fake_rest_one_voice(_method, _table, _token, **_kwargs):
    return _Response(
        200,
        [{"display_name": "Mom", "provider_voice_id": "el_voice_123", "language": "en"}],
    )


async def _fake_rest_exploding(_method, _table, _token, **_kwargs):
    raise RuntimeError("supabase is down")


def _rest_on_plan(tier: str):
    """A `rest` double whose `subscriptions` table says the caller is on `tier`.

    Every other table stays empty, so plan resolution is the only thing the
    stub changes.
    """

    async def _rest(_method, table, _token, **_kwargs):
        if str(table).startswith("subscriptions"):
            if tier == "free":
                return _Response(200, [])
            return _Response(
                200,
                [{
                    "user_id": "11111111-1111-1111-1111-111111111111",
                    "status": "active",
                    "tier": tier,
                    "current_period_end": "2099-01-01T00:00:00+00:00",
                }],
            )
        return _Response(200, [])

    return _rest


_fake_rest_empty = _fake_rest
_fake_rest_pro = _rest_on_plan("pro")


# ── Read-aloud must survive a cloud provider being enabled ───────────────────
#
# Reported as "text to voice is malfunctioning and user cannot use it". Setting
# TTS_SERVICE=elevenlabs *replaced* the catalogue instead of extending it, so
# every voice became a paid cloud voice: Free and Basic had none at all, and the
# browser tier — free, offline, and the documented default — disappeared.

def test_browser_voices_are_offered_even_when_a_cloud_provider_is_configured(monkeypatch):
    monkeypatch.setenv("TTS_SERVICE", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    from services.tts.factory import get_tts_service

    get_tts_service.cache_clear()
    try:
        voices = client.get("/tts/voices").json()["voices"]
    finally:
        get_tts_service.cache_clear()
    providers = {v["provider"] for v in voices}
    assert "browser" in providers, "the free tier vanished when cloud was enabled"


def test_a_browser_voice_never_requires_signing_in(monkeypatch):
    """Browser voices cost nothing and run on the client. Gating them behind an
    account is what made read-aloud unusable."""
    monkeypatch.setenv("TTS_SERVICE", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    from services.tts.factory import get_tts_service

    get_tts_service.cache_clear()
    try:
        voices = client.get("/tts/voices").json()["voices"]
        browser_id = next(v["id"] for v in voices if v["provider"] == "browser")
        response = client.post("/tts/speak", json={"text": "hello", "voice_id": browser_id})
    finally:
        get_tts_service.cache_clear()
    assert response.status_code == 200, response.text
    assert response.json()["speak_locally"] is True


def test_an_unknown_voice_falls_back_to_free_rather_than_a_paywall(monkeypatch):
    """A stale id in localStorage must not be answered with 'sign in' or a bill."""
    monkeypatch.setenv("TTS_SERVICE", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    from services.tts.factory import get_tts_service

    get_tts_service.cache_clear()
    try:
        response = client.post("/tts/speak", json={"text": "hi", "voice_id": "stale-id-123"})
    finally:
        get_tts_service.cache_clear()
    assert response.status_code != 401
    assert "unknown voice" in response.json()["detail"].lower()
