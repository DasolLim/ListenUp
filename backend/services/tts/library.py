"""Every voice a caller may use, and which service renders each one.

This decision used to live in the HTTP route, spread across four places: which
ids belong to the browser tier, which to the cloud, what
`getattr(service, "clone_voice", None)` means, and the rule that `TTS_SERVICE`
must not be consulted when choosing a *voice*. Each was a chance to get the
paywall wrong in one direction or the other, and one already had been —
enabling ElevenLabs replaced the catalogue instead of adding to it, leaving Free
and Basic users with no voices at all.

One object now answers all of it:

    library = VoiceLibrary.configured()
    await library.catalogue(language)          # everything selectable
    await library.is_billable(voice_id)        # does speaking this cost money?
    await library.speak(text, voice_id, ...)   # rendered by whichever tier owns it
    library.can_clone / clone(...) / forget(...)

The two rules it exists to keep:

1. **Browser voices are the floor.** They cost nothing, work offline and need no
   account, so they are added to every deployment and every tier — never
   substituted for.
2. **An id we do not recognise resolves to the free tier**, never the paid one.
   A stale value in localStorage or a deleted custom voice is a guess, and a
   guess must not be answered with a paywall or a bill.
"""

import logging
from typing import cast

from services.tts.base import ShapeableTts, Speech, TtsError, TtsService, Voice
from services.tts.browser import BrowserTtsService
from services.tts.factory import get_tts_service

logger = logging.getLogger("listenup.tts.library")


class VoiceLibrary:
    def __init__(self, browser: TtsService, cloud: TtsService | None = None) -> None:
        self._browser = browser
        self._cloud = cloud

    @classmethod
    def configured(cls) -> "VoiceLibrary":
        """The library this deployment offers.

        The browser tier is constructed directly rather than through the
        factory: `TTS_SERVICE` picks the *cloud* provider, and reading it to
        decide the free tier is what broke read-aloud — Pro also spent its
        30-minute allowance on lines a browser would have read for nothing.
        """
        service = get_tts_service()
        cloud = service if service.renders_audio else None
        return cls(BrowserTtsService(), cloud)

    # ── What can be spoken ───────────────────────────────────────────────────

    async def catalogue(self, language: str | None = None) -> list[Voice]:
        voices = list(await self._browser.voices(language))
        if self._cloud is not None:
            voices.extend(await self._cloud.voices(language))
        return voices

    async def _cloud_ids(self) -> set[str]:
        if self._cloud is None:
            return set()
        return {voice.id for voice in await self._cloud.voices()}

    async def is_billable(self, voice_id: str) -> bool:
        """Whether speaking this voice costs money, and so needs a paying caller.

        Asked of the *voice*, not of the deployment. A browser voice is free on
        every tier and needs no account even where a cloud provider exists.
        """
        return voice_id in await self._cloud_ids()

    async def speak(
        self, text: str, voice_id: str, expressiveness: float | None = None
    ) -> Speech:
        """Render `text`, through whichever tier owns `voice_id`.

        `expressiveness` is only handed to a service that declares it can act on
        one: the browser tier's `speak` takes two arguments, because the client
        does the rendering, and passing a keyword it does not accept would be a
        TypeError rather than a graceful ignore.
        """
        cloud = self._cloud is not None and voice_id in await self._cloud_ids()
        if not cloud and not await self._known_to_browser(voice_id):
            logger.info("tts_unknown_voice id=%r — answering from the free tier", voice_id)
        service = self._cloud if cloud and self._cloud is not None else self._browser
        if expressiveness is not None and service.supports_expressiveness:
            return await cast(ShapeableTts, service).speak(
                text, voice_id, expressiveness=expressiveness
            )
        return await service.speak(text, voice_id)

    async def _known_to_browser(self, voice_id: str) -> bool:
        return any(voice.id == voice_id for voice in await self._browser.voices())

    # ── Cloning, which only some providers can do ────────────────────────────

    @property
    def can_clone(self) -> bool:
        return self._cloud is not None and self._cloud.supports_cloning

    async def clone(self, name: str, sample: bytes, seconds: float) -> str:
        """Build a provider-side voice from a consented recording.

        Consent is the caller's to establish and record before this is reached
        (see `app.custom_voices`); this only enforces sample quality.
        """
        if self._cloud is None or not self._cloud.supports_cloning:
            raise TtsError(
                "Custom voices need the cloud voice provider. Ask an admin to enable it "
                "(TTS_SERVICE=elevenlabs); preset voices keep working meanwhile."
            )
        return await self._cloud.clone_voice(name, sample, seconds)

    async def forget(self, provider_voice_id: str) -> None:
        """Delete a cloned voice at the provider.

        A no-op when no provider can clone: deletion is a legal obligation
        (BIPA/GDPR), and refusing because the provider is gone would strand our
        own row and leave the user unable to remove their own biometric data.
        """
        if self._cloud is None or not self._cloud.supports_cloning:
            return
        await self._cloud.delete_voice(provider_voice_id)
