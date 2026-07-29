"""Browser-rendered voices (the free default) — and the CI/dev stub.

This service never synthesises audio server-side. It publishes a curated list of
voices and tells the client to speak them with `window.speechSynthesis`, which
costs nothing, works offline, and needs no API key.

`browser_hint` is matched (case-insensitively, as a substring) against the OS
voice list in the browser. Hints are ordered most- to least-specific per OS, so
a machine with the good Apple/Google voices uses them and anything else falls
back to the platform default for that language.
"""

from services.tts.base import Speech, TtsError, TtsService, Voice, assert_speakable

# Curated per language: at least one female and one male, plus a neutral
# fallback. Labels are what the user actually sees, so they name the voice's
# character rather than the vendor's model string.
BROWSER_VOICES: tuple[Voice, ...] = (
    Voice(
        id="browser-en-female",
        label="Aria — English (female)",
        language="en",
        gender="female",
        provider="browser",
        browser_hint=(
            "Samantha|Google US English|Microsoft Aria|Microsoft Zira"
            "|Karen|Moira|en-us-x-tpf|female"
        ),
    ),
    Voice(
        id="browser-en-male",
        label="Miles — English (male)",
        language="en",
        gender="male",
        provider="browser",
        browser_hint=(
            "Daniel|Google UK English Male|Microsoft Guy|Microsoft David"
            "|Alex|Fred|en-us-x-tpd|male"
        ),
    ),
    Voice(
        id="browser-en-neutral",
        label="System default — English",
        language="en",
        gender="neutral",
        provider="browser",
        browser_hint="",
    ),
    Voice(
        id="browser-ko-female",
        label="지아 Jia — Korean (female)",
        language="ko",
        gender="female",
        provider="browser",
        browser_hint=(
            "Yuna|Google 한국의|Microsoft Heami|Microsoft SunHi|Sora|ko-kr-x-ism|female"
        ),
    ),
    Voice(
        id="browser-ko-male",
        label="민준 Minjun — Korean (male)",
        language="ko",
        gender="male",
        provider="browser",
        browser_hint=(
            "Minsu|Microsoft InJoon|Microsoft GookMin|Jina|ko-kr-x-koc|male"
        ),
    ),
    Voice(
        id="browser-ko-neutral",
        label="System default — Korean",
        language="ko",
        gender="neutral",
        provider="browser",
        browser_hint="",
    ),
)


class BrowserTtsService(TtsService):
    """Default service: describes voices, delegates rendering to the client."""

    async def voices(self, language: str | None = None) -> list[Voice]:
        if language is not None:
            assert_speakable(language)
            return [v for v in BROWSER_VOICES if v.language == language]
        return list(BROWSER_VOICES)

    async def speak(self, text: str, voice_id: str) -> Speech:
        # Reject ids we don't publish. Silently falling back to a default voice
        # is worse than an error: a stale or deleted custom-voice id would speak
        # in a stranger's voice with nothing to tell the user why.
        if not any(v.id == voice_id for v in BROWSER_VOICES):
            raise TtsError(
                f"Unknown voice '{voice_id}'. It may have been removed — pick another voice."
            )
        # No server-side audio: the client speaks this itself. Returning
        # `speak_locally` keeps the API shape identical to the cloud path so the
        # frontend has one code path for both tiers.
        return Speech(
            voice_id=voice_id,
            speak_locally=True,
            characters=len(text),
        )
