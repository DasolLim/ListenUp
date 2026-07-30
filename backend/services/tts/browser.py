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

# Curated per language: three female and three male, plus a neutral fallback.
# Labels are what the user actually sees, so they name the voice's character
# rather than the vendor's model string.
#
# Why three of each rather than one: `browser_hint` resolves to a *different OS
# voice* per entry, so these are genuinely distinct voices — not the same voice
# at three pitches, which is what the shape sliders already provide. Each entry
# leads with a different first-choice hint so a machine with several installed
# voices spreads across them instead of collapsing onto one.
#
# Ordering within a hint list is most- to least-specific. The trailing gender
# word is a last resort for Android/Linux voices named only by locale, and the
# final fallback (any voice for the right language) lives in `pickBrowserVoice`.
BROWSER_VOICES: tuple[Voice, ...] = (
    # ── English, female ──
    Voice(
        id="browser-en-female",
        label="Aria — warm, everyday (female)",
        language="en",
        gender="female",
        provider="browser",
        browser_hint=(
            "Samantha|Google US English|Microsoft Aria|Microsoft Zira"
            "|Karen|Moira|en-us-x-tpf|female"
        ),
    ),
    Voice(
        id="browser-en-female-bright",
        label="Nova — bright, expressive (female)",
        language="en",
        gender="female",
        provider="browser",
        browser_hint=(
            "Microsoft Jenny|Google UK English Female|Serena|Allison|Ava"
            "|Microsoft Michelle|en-gb-x-gba|en-us-x-iol|female"
        ),
    ),
    Voice(
        id="browser-en-female-calm",
        label="Willow — calm, measured (female)",
        language="en",
        gender="female",
        provider="browser",
        browser_hint=(
            "Fiona|Tessa|Microsoft Sonia|Microsoft Emma|Kate|Susan|Victoria"
            "|en-au-x-aub|en-us-x-tpc|female"
        ),
    ),
    # ── English, male ──
    Voice(
        id="browser-en-male",
        label="Miles — clear, steady (male)",
        language="en",
        gender="male",
        provider="browser",
        browser_hint=(
            "Daniel|Google UK English Male|Microsoft Guy|Microsoft David"
            "|Alex|Fred|en-us-x-tpd|male"
        ),
    ),
    Voice(
        id="browser-en-male-deep",
        label="Atlas — deep, grounded (male)",
        language="en",
        gender="male",
        provider="browser",
        browser_hint=(
            "Microsoft Ryan|Microsoft Mark|Rishi|Aaron|Reed|Lee|Oliver"
            "|en-gb-x-gbb|en-us-x-iom|male"
        ),
    ),
    Voice(
        id="browser-en-male-light",
        label="Finn — light, friendly (male)",
        language="en",
        gender="male",
        provider="browser",
        browser_hint=(
            "Microsoft Brandon|Microsoft Christopher|Tom|Junior|Ralph|Arthur"
            "|en-au-x-auc|en-us-x-sfg|male"
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
    # ── Korean, female ──
    Voice(
        id="browser-ko-female",
        label="지아 Jia — warm, everyday (female)",
        language="ko",
        gender="female",
        provider="browser",
        browser_hint=(
            "Yuna|Google 한국의|Microsoft Heami|Microsoft SunHi|Sora|ko-kr-x-ism|female"
        ),
    ),
    Voice(
        id="browser-ko-female-bright",
        label="하윤 Hayun — bright, expressive (female)",
        language="ko",
        gender="female",
        provider="browser",
        browser_hint=(
            "Microsoft SunHi|Microsoft JiMin|Microsoft SeoHyeon|Sora|Narae"
            "|ko-kr-x-kod|female"
        ),
    ),
    Voice(
        id="browser-ko-female-calm",
        label="서연 Seoyeon — calm, measured (female)",
        language="ko",
        gender="female",
        provider="browser",
        browser_hint=(
            "Microsoft SoonBok|Microsoft YuJin|Microsoft BongJin|Heami|Yuna"
            "|ko-kr-x-ism|female"
        ),
    ),
    # ── Korean, male ──
    Voice(
        id="browser-ko-male",
        label="민준 Minjun — clear, steady (male)",
        language="ko",
        gender="male",
        provider="browser",
        browser_hint=(
            "Minsu|Microsoft InJoon|Microsoft GookMin|Jina|ko-kr-x-koc|male"
        ),
    ),
    Voice(
        id="browser-ko-male-deep",
        label="도현 Dohyun — deep, grounded (male)",
        language="ko",
        gender="male",
        provider="browser",
        browser_hint=(
            "Microsoft GookMin|Microsoft Hyunsu|Microsoft BongJin|Minsu"
            "|ko-kr-x-koc|male"
        ),
    ),
    Voice(
        id="browser-ko-male-light",
        label="지호 Jiho — light, friendly (male)",
        language="ko",
        gender="male",
        provider="browser",
        browser_hint=(
            "Microsoft InJoon|Microsoft SeoHyeon|Jina|Minsu|ko-kr-x-kob|male"
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
