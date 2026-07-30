"""Text-to-speech interface.

Why TTS exists here: translation that a user has to *read* still leaves them
doing the work. Speaking the translated line out loud makes ListenUp behave
like a third-party interpreter — the other person hears their own language.

Two tiers, deliberately:

* **Browser** (`speechSynthesis`) is the default. Free, offline, instant, and
  every modern OS ships male and female voices for both English and Korean. No
  API key, so the feature works in dev and CI without spend (INTRODUCTION §6).
  The backend only *describes* these voices; the browser renders them.
* **Cloud** (ElevenLabs) is opt-in for higher quality and custom voices. It
  returns audio bytes the client plays.

Custom (cloned) voices are biometric data and are gated exactly like voice
profiles in Phase 3: explicit consent from the person being cloned, versioned
consent text, deletion and export. Speaking as someone who never agreed to it
is impersonation, not a feature.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from services.translate.base import SUPPORTED_LANGUAGES

# Consent copy shown to the person whose voice is cloned. Bump on any wording
# change so stored records stay auditable (mirrors CONSENT_TEXT_VERSION in
# app/routes/profiles.py).
VOICE_CLONE_CONSENT_VERSION = "2026-07-26.v1"

VOICE_CLONE_CONSENT_TEXT = (
    "I agree that ListenUp may create a synthetic copy of my voice from this "
    "recording, and use it to read translated text aloud in this account. I "
    "understand this is biometric data, that I can ask for it to be deleted or "
    "exported at any time, and that I am the person speaking in this recording."
)

# Minimum usable clone sample. Shorter than this and every provider produces
# something that sounds nothing like the speaker.
MIN_CLONE_SECONDS = 30.0
MAX_CLONE_SECONDS = 180.0


class TtsError(Exception):
    """User-presentable synthesis failure (bad voice, provider down, no consent)."""


@dataclass(frozen=True)
class Voice:
    """One selectable voice.

    `provider` tells the client how to speak it: "browser" voices are rendered
    locally via speechSynthesis (`browser_hint` matches against the OS voice
    list); "cloud" and "custom" voices come back as audio from /tts/speak.
    """

    id: str
    label: str
    language: str
    gender: str  # "female" | "male" | "neutral"
    provider: str  # "browser" | "cloud" | "custom"
    browser_hint: str = ""  # substring matched against OS voice names
    owner_name: str = ""  # custom voices only: whose voice this is

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "language": self.language,
            "gender": self.gender,
            "provider": self.provider,
            "browser_hint": self.browser_hint,
            "owner_name": self.owner_name,
        }


@dataclass(frozen=True)
class Speech:
    """Synthesised audio, or an instruction to speak locally."""

    voice_id: str
    # Empty for browser voices — the client renders those itself.
    audio: bytes = field(default=b"", repr=False)
    mime_type: str = ""
    characters: int = 0  # billed characters, for the cost audit
    cached: bool = False
    speak_locally: bool = False


def assert_speakable(language: str) -> None:
    """TTS follows the same launch scope as translation (en/ko)."""
    if language not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise TtsError(f"No voices for language '{language}'. Supported: {supported}.")


class TtsService(ABC):
    # Whether `speak()` accepts an `expressiveness` keyword. Only services that
    # render audio server-side can act on it: the browser tier hands rendering to
    # the client, which has no such control. The route checks this rather than
    # assuming every service takes the argument.
    supports_expressiveness: bool = False

    @abstractmethod
    async def voices(self, language: str | None = None) -> list[Voice]:
        """Selectable voices, optionally filtered to one language."""

    @abstractmethod
    async def speak(self, text: str, voice_id: str) -> Speech:
        """Render `text` in `voice_id`.

        Services that set `supports_expressiveness` also accept an
        `expressiveness: float` keyword (0–1) controlling how much the delivery
        varies.
        """
