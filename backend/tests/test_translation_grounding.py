"""The cultural pass is grounded in the slang KB.

Before this, `services/openrouter` built its prompt from model memory alone. That
works for slang that predates the training cutoff — which is why an earlier QA
round scored 18/18 on `bussin`, `갓생`, `인싸` — and fails *confidently* on
anything newer, returning a plausible wrong meaning. A wrong meaning delivered
with confidence is worse for the reader than an admission of ignorance, which is
why `grounded` is now on the wire.

These tests stub the model and the KB: the point is the wiring and the failure
behaviour, not whether gpt-4o is any good (the real-service QA covers that).
"""

import asyncio

import pytest

from services.genz.base import RetrievedTerm, SlangTerm
from services.openrouter.base import EnhancedTranslation, SlangNote


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    from services.openrouter.real import OpenRouterTranslationService

    return OpenRouterTranslationService()


class _KB:
    """A KB with one known term, recording what it was asked and told."""

    def __init__(self, terms: list[SlangTerm] | None = None) -> None:
        self.terms = terms or []
        self.gaps: list[str] = []

    def search(self, query: str, k: int = 3) -> list[RetrievedTerm]:  # noqa: ARG002
        return [
            RetrievedTerm(term=t, score=0.9)
            for t in self.terms
            if t.term.lower() in query.lower()
        ]

    def log_gap(self, query: str) -> None:
        self.gaps.append(query)


def _install(monkeypatch, kb: _KB, notes: list[SlangNote], captured: dict | None = None):
    """Point retrieval at `kb` and make the model return `notes`."""
    import services.genz as genz_pkg

    monkeypatch.setattr(genz_pkg, "get_slang_kb", lambda: kb)

    async def _complete(  # noqa: ARG001
        _self, text, target_lang, nudge, grounding=(), model=None, reasoning_effort=None
    ):
        if captured is not None:
            captured["grounding"] = list(grounding)
        payload = {
            "translation": "translated",
            "register": "casual",
            "slang_notes": [
                {"phrase": n.phrase, "meaning": n.meaning,
                 "cultural_context": "", "equivalent": ""}
                for n in notes
            ],
        }
        import json as _json

        return _json.dumps(payload), 42

    from services.openrouter.real import OpenRouterTranslationService

    monkeypatch.setattr(OpenRouterTranslationService, "_complete", _complete)


KNOWN = SlangTerm(term="갓생", meaning="a disciplined, productive life")


def test_a_known_phrase_is_marked_grounded(service, monkeypatch):
    kb = _KB([KNOWN])
    _install(monkeypatch, kb, [SlangNote(phrase="갓생", meaning="productive life")])

    result = asyncio.run(service.translate("갓생 살고 싶다", "en"))

    assert [n.grounded for n in result.slang_notes] == [True]
    assert kb.gaps == [], "a term the KB supplied must not be logged as a gap"


def test_the_kb_definition_reaches_the_prompt(service, monkeypatch):
    """Retrieval that never makes it into the prompt grounds nothing."""
    captured: dict = {}
    _install(monkeypatch, _KB([KNOWN]), [SlangNote(phrase="갓생", meaning="x")], captured)

    asyncio.run(service.translate("갓생 살고 싶다", "en"))

    assert [t.term for t in captured["grounding"]] == ["갓생"]


def test_an_unknown_phrase_is_ungrounded_and_logged_as_a_gap(service, monkeypatch):
    """The whole point: the translation still ships, but the note is marked as
    the model's recall rather than a known definition, and the gap is recorded
    so curation can close it."""
    kb = _KB([KNOWN])
    _install(monkeypatch, kb, [SlangNote(phrase="쌉느좋", meaning="something newly coined")])

    result = asyncio.run(service.translate("이거 완전 쌉느좋", "en"))

    assert result is not None, "an unknown term must not cost the user their translation"
    assert [n.grounded for n in result.slang_notes] == [False]
    assert kb.gaps == ["쌉느좋"]


def test_a_mixed_message_marks_each_note_independently(service, monkeypatch):
    kb = _KB([KNOWN])
    _install(monkeypatch, kb, [
        SlangNote(phrase="갓생", meaning="productive life"),
        SlangNote(phrase="쌉느좋", meaning="newly coined"),
    ])

    result = asyncio.run(service.translate("갓생 쌉느좋", "en"))

    assert {n.phrase: n.grounded for n in result.slang_notes} == {"갓생": True, "쌉느좋": False}
    assert kb.gaps == ["쌉느좋"]


def test_retrieval_failure_degrades_to_ungrounded_rather_than_failing(service, monkeypatch):
    """Translation must not fail because retrieval did. Grounding is an
    improvement to the cultural pass, never a precondition for it."""

    class _Broken:
        def search(self, *_a, **_k):
            raise RuntimeError("pgvector is down")

        def log_gap(self, *_a, **_k):
            raise RuntimeError("still down")

    import services.genz as genz_pkg

    monkeypatch.setattr(genz_pkg, "get_slang_kb", lambda: _Broken())

    async def _complete(  # noqa: ARG001
        _self, text, target_lang, nudge, grounding=(), model=None, reasoning_effort=None
    ):
        assert grounding == [] or grounding == (), "a broken KB must ground nothing"
        import json as _json

        return _json.dumps({
            "translation": "translated", "register": "casual",
            "slang_notes": [{"phrase": "갓생", "meaning": "m",
                             "cultural_context": "", "equivalent": ""}],
        }), 10

    from services.openrouter.real import OpenRouterTranslationService

    monkeypatch.setattr(OpenRouterTranslationService, "_complete", _complete)

    result = asyncio.run(service.translate("갓생", "en"))
    assert result is not None
    assert [n.grounded for n in result.slang_notes] == [False]


def test_the_prompt_version_was_bumped_for_grounding():
    """The Redis cache key includes PROMPT_VERSION. Changing the prompt without
    bumping it serves pre-grounding answers until the TTL expires."""
    from services.openrouter.real import PROMPT_VERSION

    assert PROMPT_VERSION != "2026-07-23.v4", "the pre-grounding version is still in use"


def test_the_cache_key_includes_the_retrieved_terms(service, monkeypatch):
    """The same sentence grounded in a larger KB is a different answer. Keying
    only on text would hide new curation behind a 7-day TTL."""
    from services.openrouter.real import PROMPT_VERSION
    from services.translate.cache import cache_key

    empty = cache_key("llm", "갓생", "en", f"{service.model}:{PROMPT_VERSION}:")
    grounded = cache_key("llm", "갓생", "en", f"{service.model}:{PROMPT_VERSION}:갓생")
    assert empty != grounded


class TestPhraseCoverage:
    """The model quotes the span it annotates, not the headword. Real QA output:
    a note on `zero rizz` against a KB entry for `rizz`. Under-reporting makes
    good answers look untrusted; over-reporting is worse, because `grounded` is
    the signal a reader would act on."""

    @pytest.mark.parametrize("term,phrase", [
        ("rizz", "zero rizz"),          # observed in QA
        ("rizz", "rizz"),
        ("touch grass", "go touch grass"),
        ("ate", "ate that presentation"),
        ("no cap", "no cap fr"),
        ("갓생", "갓생 살았다"),           # Korean has no word boundary to lean on
        ("꿀잼", "완전 꿀잼이었어"),
        ("썸", "썸 타다"),                # observed in QA; one syllable is a real term
        ("썸", "썸타는 것 같아"),
    ])
    def test_a_wider_quote_still_counts_as_covered(self, term, phrase):
        from services.openrouter.real import _covers

        assert _covers(term, phrase)

    @pytest.mark.parametrize("term,phrase", [
        ("mid", "midnight"),            # the reason this isn't a substring check
        ("ate", "hesitated"),
        ("ate", "later"),
        ("sus", "suspension"),
        ("bet", "better"),
        ("stan", "understand"),
        ("갓생", "인생"),                # a suffix match is not a stem match
        ("꿀잼", "개꿀잼"),               # 개- is a prefix; the KB term is not the stem
        ("", "anything"),
        ("rizz", ""),
    ])
    def test_an_incidental_match_is_not_coverage(self, term, phrase):
        from services.openrouter.real import _covers

        assert not _covers(term, phrase)

    def test_the_known_false_positive_is_recorded_not_claimed_fixed(self):
        """`썸` (a crush) is a KB term and also the first syllable of 썸네일
        (thumbnail). Prefix-of-token matching cannot tell them apart. Pinned here
        so the limitation is visible rather than discovered later as a bug — see
        `_covers`, which explains why the trade lands this way."""
        from services.openrouter.real import _covers

        assert _covers("썸", "썸네일"), "if this now fails, the matcher improved"


def test_grounded_survives_the_wire_shape():
    """The route serialises notes with `__dict__`, so the flag must be a real
    field or the client silently never sees it."""
    note = SlangNote(phrase="갓생", meaning="m", grounded=True)
    assert note.__dict__["grounded"] is True
    assert EnhancedTranslation(
        translation="t", register="r", slang_notes=[note], model="m"
    ).slang_notes[0].grounded is True


def test_confidence_can_never_contradict_grounded(service, monkeypatch):
    """Two fields carrying one fact can drift apart. They are written together in
    `_mark_grounding` precisely so they can't, and this pins that."""
    _install(monkeypatch, _KB([KNOWN]), [
        SlangNote(phrase="갓생", meaning="m"),
        SlangNote(phrase="쌉느좋", meaning="m"),
    ])

    result = asyncio.run(service.translate("갓생 쌉느좋", "en"))

    for note in result.slang_notes:
        assert note.confidence == ("high" if note.grounded else "low")
    assert {n.confidence for n in result.slang_notes} == {"high", "low"}


def test_a_cached_response_keeps_its_grounding_verdict(service, monkeypatch):
    """The cache stores notes as plain dicts. If `grounded`/`confidence` are
    dropped on the way in or out, the second reader of a phrase sees an
    unverified note for a KB term — the flag would flap by cache state."""
    _install(monkeypatch, _KB([KNOWN]), [SlangNote(phrase="갓생", meaning="m")])

    first = asyncio.run(service.translate("갓생 살고 싶다", "en"))
    second = asyncio.run(service.translate("갓생 살고 싶다", "en"))

    assert second.cached is True, "the second call should have been served warm"
    assert [(n.grounded, n.confidence) for n in second.slang_notes] == \
           [(n.grounded, n.confidence) for n in first.slang_notes]
