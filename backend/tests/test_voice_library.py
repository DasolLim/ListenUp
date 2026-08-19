"""Which service speaks a voice — the decision that used to live in the route.

The route knew every detail of it: which ids belong to the browser tier, which
to the cloud, what `getattr(service, "clone_voice", None)` means, and that
`TTS_SERVICE` must not be read when choosing a *voice*. Each of those was a
place to get the paywall wrong in one direction or the other, and one of them
already had been: turning ElevenLabs on replaced the catalogue instead of adding
to it, so Free and Basic users — who cannot use cloud voices at all — were left
with no voices whatsoever.

Only the providers are stubbed here, because they are the external tools
(INTRODUCTION §6): the browser tier is the real one, since it costs nothing.
"""

import pytest

from services.tts.base import Speech, TtsError, TtsService, Voice
from services.tts.browser import BrowserTtsService
from services.tts.library import VoiceLibrary


class StubCloud(TtsService):
    """A provider that renders audio, bills for it, and can clone."""

    supports_expressiveness = True
    renders_audio = True
    supports_cloning = True

    def __init__(self) -> None:
        self.spoken: list[tuple[str, str, float | None]] = []
        self.cloned: list[str] = []
        self.deleted: list[str] = []

    async def voices(self, language: str | None = None) -> list[Voice]:
        all_voices = [
            Voice("cloud-en", "Cloud English", "en", "female", "cloud"),
            Voice("cloud-ko", "Cloud Korean", "ko", "male", "cloud"),
        ]
        return [v for v in all_voices if language is None or v.language == language]

    async def speak(
        self, text: str, voice_id: str, expressiveness: float | None = None
    ) -> Speech:
        self.spoken.append((text, voice_id, expressiveness))
        return Speech(voice_id=voice_id, audio=b"audio", mime_type="audio/mpeg",
                      characters=len(text))

    async def clone_voice(self, name: str, sample: bytes, seconds: float) -> str:
        self.cloned.append(name)
        return f"provider-{name}"

    async def delete_voice(self, voice_id: str) -> None:
        self.deleted.append(voice_id)


def free_only() -> VoiceLibrary:
    return VoiceLibrary(BrowserTtsService())


def with_cloud() -> tuple[VoiceLibrary, StubCloud]:
    cloud = StubCloud()
    return VoiceLibrary(BrowserTtsService(), cloud), cloud


# ── The paywall runs on the voice, not on the deployment ─────────────────────


@pytest.mark.anyio
async def test_turning_on_a_cloud_provider_adds_voices_rather_than_replacing_them():
    """The shipped bug. Browser voices cost nothing, work offline and need no
    account, so they are the floor for every tier and every deployment."""
    library, _ = with_cloud()
    ids = {voice.id for voice in await library.catalogue()}
    assert "browser-en-female" in ids, "enabling a cloud provider hid the free voices"
    assert "cloud-en" in ids


@pytest.mark.anyio
async def test_a_browser_voice_is_free_even_where_a_cloud_provider_exists():
    """Otherwise a Free user on a deployment that happens to have ElevenLabs
    configured would be charged for a voice their own browser rendered."""
    library, cloud = with_cloud()
    assert await library.is_billable("browser-en-female") is False
    speech = await library.speak("hello", "browser-en-female")
    assert speech.speak_locally is True
    assert cloud.spoken == [], "a browser voice reached the paid provider"


@pytest.mark.anyio
async def test_a_cloud_voice_is_billable():
    library, _ = with_cloud()
    assert await library.is_billable("cloud-en") is True


@pytest.mark.anyio
async def test_an_unknown_voice_id_never_routes_to_the_paid_provider():
    """A stale value in localStorage or a deleted custom voice is a guess, and a
    guess must not meet a paywall or a bill. It resolves to the free tier, which
    then says it does not know that voice."""
    library, cloud = with_cloud()
    assert await library.is_billable("deleted-custom-voice") is False
    with pytest.raises(TtsError, match="Unknown voice"):
        await library.speak("hello", "deleted-custom-voice")
    assert cloud.spoken == []


# ── Capabilities are asked for, not guessed at ───────────────────────────────


@pytest.mark.anyio
async def test_expressiveness_only_reaches_a_service_that_can_render_it():
    """The browser tier hands rendering to the client, so its `speak` takes two
    arguments — passing a keyword it does not accept is a TypeError, and a user
    who set the slider on a cloud voice could then no longer speak with a
    browser one."""
    library, cloud = with_cloud()
    await library.speak("hello", "browser-en-female", expressiveness=0.9)  # must not raise
    await library.speak("hello", "cloud-en", expressiveness=0.9)
    assert cloud.spoken == [("hello", "cloud-en", 0.9)]


@pytest.mark.anyio
async def test_cloning_without_a_provider_says_what_is_missing():
    """It used to be `getattr(service, "clone_voice", None)` at three call sites.
    A missing capability should read as a sentence a user can act on, not as an
    attribute that happens not to be there."""
    library = free_only()
    assert library.can_clone is False
    with pytest.raises(TtsError, match="TTS_SERVICE"):
        await library.clone("Mom", b"\x00" * 32000, 30.0)


@pytest.mark.anyio
async def test_cloning_and_deleting_go_to_the_provider_that_can_do_them():
    library, cloud = with_cloud()
    assert library.can_clone is True
    voice_id = await library.clone("Mom", b"\x00" * 32000, 30.0)
    assert voice_id == "provider-Mom"
    await library.forget(voice_id)
    assert cloud.deleted == ["provider-Mom"]


@pytest.mark.anyio
async def test_forgetting_a_voice_with_no_provider_is_not_an_error():
    """Deletion is a legal obligation (BIPA/GDPR). If the provider is gone there
    is nothing of theirs left to delete, and refusing would strand our own row
    — the user would be unable to remove their own biometric data."""
    await free_only().forget("provider-Mom")


# ── The catalogue ────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_the_language_filter_reaches_both_tiers():
    library, _ = with_cloud()
    ko = await library.catalogue("ko")
    assert {v.language for v in ko} == {"ko"}
    assert "cloud-ko" in {v.id for v in ko}
