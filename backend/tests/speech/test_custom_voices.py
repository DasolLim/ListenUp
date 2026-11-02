"""A user's cloned voices: ours and the provider's, kept in step.

Cloned voices are biometric data, so the rules here are the Phase 3 enrolment
rules (INTRODUCTION §6) and they are enforced in code rather than in the UI. The
route used to hold all of this inline — the consent gate, the cap, the orphan
cleanup, the PostgREST error translation — which meant every rule was reachable
only through an HTTP request, and the consent gate in particular was one `if`
in a handler that anybody adding a second create path would have had to
remember to copy.

Only the database and the voice provider are stubbed; they are the external
things.
"""

import httpx
import pytest
from fastapi import HTTPException

from app import custom_voices as store_module
from app.custom_voices import CustomVoiceStore
from services.tts.base import Speech, TtsError, TtsService, Voice
from services.tts.browser import BrowserTtsService
from services.tts.library import VoiceLibrary


class StubCloud(TtsService):
    renders_audio = True
    supports_cloning = True

    def __init__(self, *, delete_fails: bool = False) -> None:
        self.cloned: list[str] = []
        self.deleted: list[str] = []
        self._delete_fails = delete_fails

    async def voices(self, language: str | None = None) -> list[Voice]:
        return []

    async def speak(self, text: str, voice_id: str) -> Speech:
        return Speech(voice_id=voice_id)

    async def clone_voice(self, name: str, sample: bytes, seconds: float) -> str:
        self.cloned.append(name)
        return f"provider-{name}"

    async def delete_voice(self, voice_id: str) -> None:
        if self._delete_fails:
            raise TtsError("Couldn't delete that voice from the provider. Try again.")
        self.deleted.append(voice_id)


def response(status: int, body: object = None, text: str = "") -> httpx.Response:
    if body is not None:
        return httpx.Response(status, json=body)
    return httpx.Response(status, text=text)


@pytest.fixture
def db(monkeypatch):
    """Script PostgREST by (method, table), and record what was written."""
    calls: list[tuple[str, str]] = []
    replies: dict[tuple[str, str], httpx.Response] = {}

    async def _rest(method, path, token, *, json=None, params=None, prefer=None):
        calls.append((method, path))
        return replies.get((method, path), response(200, []))

    monkeypatch.setattr(store_module, "rest", _rest)
    return calls, replies


def store(cloud: TtsService | None = None) -> CustomVoiceStore:
    return CustomVoiceStore(
        token="t", user_id="u", library=VoiceLibrary(BrowserTtsService(), cloud)
    )


SAMPLE = b"\x00" * 32000 * 40  # 40 s at 16 kHz


# ── Consent comes first, and cannot be routed around ─────────────────────────


@pytest.mark.anyio
async def test_without_consent_nothing_reaches_the_provider(db):
    """A cloned voice can say things the person never said, so creating one
    without their agreement is impersonation rather than a missing field."""
    calls, _ = db
    cloud = StubCloud()
    with pytest.raises(HTTPException) as refused:
        await store(cloud).create(
            display_name="Mom", sample=SAMPLE, language="en",
            consent_given=False, consented_by="Mom",
        )
    assert refused.value.status_code == 400
    assert cloud.cloned == [], "a voice was built without consent"
    assert calls == [], "the database was touched before consent was checked"


@pytest.mark.anyio
async def test_a_blank_consent_signature_is_not_consent(db):
    cloud = StubCloud()
    with pytest.raises(HTTPException) as refused:
        await store(cloud).create(
            display_name="Mom", sample=SAMPLE, language="en",
            consent_given=True, consented_by="   ",
        )
    assert refused.value.status_code == 400
    assert cloud.cloned == []


# ── Nothing is left behind ───────────────────────────────────────────────────


@pytest.mark.anyio
async def test_a_failed_row_insert_removes_the_provider_side_voice(db):
    """Otherwise the clone exists at the provider with nothing here pointing at
    it — a biometric copy of someone that the person it belongs to cannot ask us
    to delete, because we no longer know it is theirs."""
    _, replies = db
    replies[("POST", "custom_voices")] = response(500, text="boom")
    cloud = StubCloud()
    with pytest.raises(HTTPException) as failed:
        await store(cloud).create(
            display_name="Mom", sample=SAMPLE, language="en",
            consent_given=True, consented_by="Mom",
        )
    assert failed.value.status_code == 502
    assert cloud.deleted == ["provider-Mom"], "an orphaned voice was left at the provider"


@pytest.mark.anyio
async def test_a_provider_that_refuses_deletion_keeps_our_row(db):
    """Our row is the handle to a voice that still exists at the provider.
    Dropping it would make the voice undeletable."""
    _, replies = db
    replies[("GET", "custom_voices")] = response(200, [{"provider_voice_id": "provider-Mom"}])
    calls, _ = db
    with pytest.raises(HTTPException) as failed:
        await store(StubCloud(delete_fails=True)).delete("v1")
    assert failed.value.status_code == 502
    assert ("DELETE", "custom_voices") not in calls, "our row was dropped anyway"


# ── Caps and failures say what they mean ─────────────────────────────────────


@pytest.mark.anyio
async def test_the_voice_cap_is_enforced_before_anything_is_built(db):
    _, replies = db
    replies[("GET", "custom_voices")] = response(200, [{"id": str(i)} for i in range(4)])
    cloud = StubCloud()
    with pytest.raises(HTTPException) as refused:
        await store(cloud).create(
            display_name="Dad", sample=SAMPLE, language="en",
            consent_given=True, consented_by="Dad",
        )
    assert refused.value.status_code == 400
    assert "delete one" in refused.value.detail.lower()
    assert cloud.cloned == []


@pytest.mark.anyio
async def test_a_missing_table_names_itself_instead_of_a_generic_failure(db):
    """A missing migration is the likeliest cause, and it used to surface as a
    bare 502 that sent people hunting through server logs."""
    _, replies = db
    replies[("GET", "custom_voices")] = response(404, text='{"code":"PGRST205"}')
    with pytest.raises(HTTPException) as failed:
        await store().rows()
    assert failed.value.status_code == 503
    assert "custom_voices" in failed.value.detail


@pytest.mark.anyio
async def test_the_picker_survives_a_lookup_failure(db):
    """Live captions and translation both need the voice list. A missing table
    or an expired token should cost you your own voices, not the ability to
    speak at all."""
    _, replies = db
    replies[("GET", "custom_voices")] = response(500, text="boom")
    assert await store().voices() == []


@pytest.mark.anyio
async def test_a_stored_voice_reaches_the_picker_shaped_like_any_other(db):
    """Cloning used to be a dead end: a voice could be created, listed in the
    studio and deleted, yet never appear in a picker."""
    _, replies = db
    replies[("GET", "custom_voices")] = response(
        200, [{"display_name": "Mom", "provider_voice_id": "provider-Mom", "language": "ko"}]
    )
    voices = await store().voices("ko")
    assert [(v.id, v.provider, v.owner_name) for v in voices] == [
        ("provider-Mom", "custom", "Mom")
    ]
    assert await store().voices("en") == [], "the language filter leaked"
