"""Real OpenRouter client. Model via OPENROUTER_MODEL (env-swappable)."""

import json
import logging
import os
import re
from dataclasses import replace

import httpx

from services.openrouter.base import (
    CulturalUnavailable,
    EnhancedTranslation,
    EnhancedTranslationService,
    ProviderError,
    SlangNote,
    coerce_enhanced,
    parse_llm_json,
)
from services.openrouter.tiers import DEFAULT_TIER, resolve
from services.translate.base import SUPPORTED_LANGUAGES, assert_supported
from services.translate.cache import cache_key, get_cache

logger = logging.getLogger("listenup.openrouter")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Derived from the tier table rather than written twice. Every request through
# `/translate/enhanced` carries a tier, so this is only reached by a direct
# service call — but a stale constant here is actively misleading: it read
# `openai/gpt-4o` long after the default tier had moved to gemini, and was
# reported as the live model on that basis. One source of truth removes the
# chance of reading the wrong one.
#
# Override with OPENROUTER_MODEL to pin a model for a one-off run.
DEFAULT_MODEL = resolve(DEFAULT_TIER).model
# Bump when the prompt changes so improvements invalidate cached translations
# instead of serving stale output for up to the cache TTL.
# Bumped for KB grounding (2026-08-10). The Redis cache key includes this, so a
# prompt change that does not bump it serves pre-grounding answers indefinitely.
PROMPT_VERSION = "2026-08-10.v5"

# The translation itself must be culturally adapted (slang → equivalent target
# slang), not literal-with-notes. Few-shot examples anchor slang-for-slang
# rendering and accurate meanings (e.g. "the tea" = gossip, "갓생" = disciplined
# productive life), which the base instruction alone tends to miss.
#
# LANGUAGE RULE (2026-07-23): the reader only speaks {target_name}, so EVERY
# human-readable field — meaning, cultural_context, register — is written in
# {target_name}, not just the translation. The few-shot examples below teach this
# explicitly; an earlier version showed English notes for en→ko and the model
# copied that, leaving Korean users with half-English explanations.
# Grounding. The model's slang knowledge is frozen at its training cutoff, so it
# is reliable on established terms and confidently wrong on recent ones — a
# plausible false meaning, which is worse for the reader than an admission of
# ignorance. Retrieved KB entries are stated as authoritative so the model
# prefers them over recall, and the KB can be updated without touching the model.
GROUNDING_PROMPT = """
KNOWN TERMS (authoritative — prefer these over your own recollection):
{terms}
If a term above appears in the source, use its meaning as given. For any slang \
NOT listed above, you may still explain it, but do not invent specificity you are \
not sure of — say what it plainly means and no more."""

SYSTEM_PROMPT = """You are a cultural translation engine for {target_name}.
Translate the user's message the way a fluent NATIVE {target_name} speaker would \
actually say or text it in the same situation: same tone, same energy, same register.

Core rule: NEVER translate slang, idioms, or memes literally. Render them with the \
closest natural {target_name} slang or idiom a native really uses. If no true \
equivalent exists, paraphrase so it still feels natural and carries the same feeling. \
The "translation" field must be this natural, adapted version, not a stiff literal one.

LANGUAGE RULE (critical): your reader reads ONLY {target_name}. Write EVERY \
human-readable field in {target_name} — "translation", "register", and for every note \
both "meaning" and "cultural_context". Do NOT write explanations in the source language. \
The only field that stays in the source language is "phrase" (it quotes the original \
slang verbatim so the reader can spot it); "equivalent" is the {target_name} expression.
When you explain a word's etymology, describe the roots IN {target_name} rather than \
quoting the source-language words — e.g. for a Korean term derived from 존나 + 잼, write \
"from a vulgar intensifier plus the word for 'fun'", NOT "from '존나' (very)". Never leave \
source-language characters inside "meaning" or "cultural_context".

For each real slang term, idiom, or cultural reference in the SOURCE, add a note whose \
"meaning" explains it accurately IN {target_name}.

Return ONLY this JSON (no prose, no code fences):
{{"translation":"<natural, culturally-adapted {target_name}>",
"register":"<the register, written in {target_name}>",
"slang_notes":[{{"phrase":"<source phrase, verbatim>","meaning":"<accurate plain meaning, in {target_name}>",\
"cultural_context":"<who says it and when, in {target_name}>","equivalent":"<the {target_name} expression you used>"}}]}}
Use slang_notes only for genuine slang/idioms/references; [] if there are none.

Examples:
English to Korean (note: every explanation is in Korean):
"That's straight fire, no cap." -> {{"translation":"이거 완전 대박이야, ㄹㅇ.",\
"register":"슬랭 많음","slang_notes":[{{"phrase":"straight fire","meaning":"엄청나게 좋다는 뜻",\
"cultural_context":"Z세대가 감탄할 때 쓰는 표현","equivalent":"대박"}},{{"phrase":"no cap",\
"meaning":"거짓말 아니고 진짜라는 뜻","cultural_context":"힙합에서 온 Z세대 표현",\
"equivalent":"ㄹㅇ (리얼)"}}]}}
"Stop capping, we all know the tea." -> {{"translation":"뻥치지 마, 우리 다 그 썰 알거든.",\
"register":"슬랭 많음","slang_notes":[{{"phrase":"capping","meaning":"거짓말하는 것",\
"cultural_context":"Z세대가 쓰는 인터넷 슬랭","equivalent":"뻥치다"}},{{"phrase":"the tea",\
"meaning":"남의 사생활에 대한 소문이나 뒷이야기","cultural_context":"드랙·흑인 문화에서 유래한 표현",\
"equivalent":"썰"}}]}}
Korean to English (note: every explanation is in English):
"그 사람 완전 인싸야." -> {{"translation":"That guy's a total social butterfly.","register":"casual",\
"slang_notes":[{{"phrase":"인싸","meaning":"a popular, socially active person who fits in everywhere",\
"cultural_context":"Korean net slang from the English word 'insider'","equivalent":"social butterfly"}}]}}
"오늘 갓생 살았다." -> {{"translation":"I absolutely crushed my day, living that disciplined best life.",\
"register":"casual","slang_notes":[{{"phrase":"갓생","meaning":"a disciplined, productive, admirable life",\
"cultural_context":"Korean net slang combining 'god' and 'life'","equivalent":"best life / grind life"}}]}}"""


def _retrieve(text: str, k: int = 4):
    """KB terms matching this text, or an empty list.

    Fails open by design: retrieval is an *improvement* to the cultural pass, not
    a precondition for it. If the KB is unavailable the translation still goes
    out ungrounded — degraded, logged, and honest about it via `grounded=False`.
    """
    try:
        from services.genz import get_slang_kb

        return [match.term for match in get_slang_kb().search(text, k=k)]
    except Exception as exc:
        logger.warning("slang_grounding_unavailable error=%s", exc)
        return []


def _log_gap(text: str) -> None:
    """Record slang the KB could not supply. This is the demand signal the
    curation loop consumes — without it the corpus never learns what it is
    missing, and 'stays current' has no mechanism behind it."""
    try:
        from services.genz import get_slang_kb

        get_slang_kb().log_gap(text)
    except Exception as exc:
        logger.debug("slang_gap_log_failed error=%s", exc)


def _covers(term: str, phrase: str) -> bool:
    """Does KB `term` account for the slang in `phrase`?

    Not equality: the model quotes the span it is annotating, which is often
    wider than the headword — QA saw `zero rizz` against a KB entry for `rizz`,
    a note whose definition *was* in the prompt being reported as ungrounded.
    Exact matching therefore under-states grounding, and `grounded` is a trust
    signal, so it should be neither over- nor under-stated.

    Matching is script-dependent because word boundaries are. English needs them
    (`mid` must not match `midnight`). Korean has none — `꿀잼` legitimately sits
    inside `꿀잼이었어` — but it is agglutinative: particles and verb endings
    attach to the *end* of a stem, so a term is required to begin a token rather
    than float anywhere inside one. That accepts `썸` in `썸 타다` (QA saw exactly
    this note) and rejects `갓생` in `인생`.

    Residual limitation, accepted: a longer word starting with the same syllables
    (`썸` in `썸네일`, thumbnail) would read as covered. It needs two coincidences
    at once — retrieval scoring that term relevant for this sentence *and* the
    model quoting the unrelated word as slang — so it is narrower than the
    under-reporting a stricter rule causes, but it is a real edge and not a
    solved one.
    """
    if not term or not phrase:
        return False
    if re.search(r"[a-z]", term):
        return re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", phrase) is not None
    return any(token.startswith(term) for token in phrase.split())


def _mark_grounding(result, grounding):
    """Flag each note as grounded or not, and log the gaps.

    A note whose phrase the KB supplied is trustworthy; one it did not is the
    model's recall, which the reader deserves to have marked. Every unmatched
    phrase is written to the gap log — that is the demand signal for curation,
    and it is collected here rather than in a separate sweep because this is the
    only moment we know both what was asked and what we could not answer.
    """
    known = [term.term.strip().lower() for term in grounding]
    notes = []
    for note in result.slang_notes:
        phrase = note.phrase.strip().lower()
        is_grounded = any(_covers(term, phrase) for term in known)
        if not is_grounded and phrase:
            _log_gap(note.phrase.strip())
        notes.append(
            replace(
                note,
                grounded=is_grounded,
                confidence="high" if is_grounded else "low",
            )
        )
    return replace(result, slang_notes=notes)


def _provider_detail(response: httpx.Response) -> str:
    """The provider's own words, trimmed to something safe to show.

    OpenRouter returns `{"error": {"message": …}}`; anything else falls back to
    the raw body. Truncated because this reaches a user-facing message, and
    length-capped rather than rewritten so an operator can still recognise the
    provider's wording when searching for it.
    """
    try:
        payload = response.json()
        message = (payload.get("error") or {}).get("message") or payload.get("message")
    except (ValueError, AttributeError):
        message = None
    text = str(message or response.text or "").strip().replace("\n", " ")
    if not text:
        return f"HTTP {response.status_code}"
    return text[:200]


class OpenRouterTranslationService(EnhancedTranslationService):
    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    @staticmethod
    def _body(text: str, system: str, model: str, reasoning_effort: str | None) -> dict:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
        }
        if reasoning_effort:
            # Several models bill thinking tokens at the completion rate and
            # emit multiples of the answer in them — measured at 92% of output
            # on one default. Capping it is the difference between a tier being
            # cheap and merely looking cheap.
            body["reasoning"] = {"effort": reasoning_effort}
        return body

    async def _complete(
        self,
        text: str,
        target_lang: str,
        strict_nudge: bool,
        grounding=(),
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> tuple[str, int]:
        target_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        system = SYSTEM_PROMPT.format(target_name=target_name)
        if grounding:
            lines = "\n".join(f"- {t.term}: {t.meaning}" for t in grounding)
            system += GROUNDING_PROMPT.format(terms=lines)
        if strict_nudge:
            system += "\nYour previous output was invalid. Return ONLY valid JSON this time."
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "HTTP-Referer": "https://listenup.app",
                    "X-Title": "ListenUp",
                },
                json=self._body(text, system, model or self.model, reasoning_effort),
            )
        if response.status_code >= 400:
            raise ProviderError(
                response.status_code,
                _provider_detail(response),
                # A 429 or a 5xx is worth a second try; a 401, 402, 403 or 404
                # is a key, a balance or a model name, and hammering it twice
                # per utterance for the length of a conversation only wastes
                # time the caption budget does not have.
                retryable=response.status_code in (408, 409, 429) or response.status_code >= 500,
            )
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        tokens = int((body.get("usage") or {}).get("total_tokens") or 0)
        return content, tokens

    async def translate(
        self, text: str, target_lang: str, tier=None
    ) -> EnhancedTranslation | None:
        assert_supported(target_lang)
        model = getattr(tier, "model", None) or self.model
        effort = getattr(tier, "reasoning_effort", None)
        cache = get_cache()
        # Retrieval happens before the cache lookup because the retrieved terms
        # are part of the key: the same sentence grounded in a larger KB is a
        # different answer, and serving the pre-grounding one would make new
        # curation invisible until the TTL expired.
        grounding = _retrieve(text)
        fingerprint = ",".join(sorted(term.term for term in grounding))
        # The model is in the key: the same sentence answered by a cheaper tier
        # is a different answer, and serving one for the other would make the
        # picker look broken in both directions.
        key = cache_key(
            "llm", text, target_lang, f"{model}:{PROMPT_VERSION}:{fingerprint}"
        )
        if (hit := await cache.get(key)) is not None:
            return EnhancedTranslation(
                translation=hit["translation"],
                register=hit["register"],
                slang_notes=[SlangNote(**n) for n in hit["slang_notes"]],
                cached=True,
                model=model,
            )

        # One retry with a strictness nudge — LLM JSON is never trusted blindly.
        # `reason` survives the loop so the give-up can say what went wrong
        # rather than leaving the user with a generic outage message for what is
        # usually a key, a balance or a model name.
        reason: str | None = None
        for attempt, nudge in enumerate((False, True)):
            try:
                content, tokens = await self._complete(
                    text, target_lang, nudge, grounding, model, effort
                )
            except ProviderError as exc:
                reason = exc.detail
                logger.warning(
                    "openrouter_request_failed attempt=%d status=%s retryable=%s reason=%s",
                    attempt, exc.status, exc.retryable, exc.detail,
                )
                if not exc.retryable:
                    break
                continue
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
                reason = f"could not reach the model provider ({type(exc).__name__})"
                logger.warning("openrouter_request_failed attempt=%d error=%s", attempt, exc)
                continue
            parsed = parse_llm_json(content)
            if parsed is None:
                reason = "the model returned something that wasn't valid JSON"
                logger.warning("openrouter_bad_json attempt=%d head=%r", attempt, content[:80])
                continue
            result = coerce_enhanced(parsed, model, tokens)
            if result is not None:
                result = _mark_grounding(result, grounding)
                await cache.set(
                    key,
                    {
                        "translation": result.translation,
                        "register": result.register,
                        "slang_notes": [n.__dict__ for n in result.slang_notes],
                    },
                )
                logger.info(
                    "openrouter_ok model=%s tokens=%d notes=%d",
                    model, tokens, len(result.slang_notes),
                )
                return result
        logger.warning("openrouter_gave_up text_len=%d reason=%s", len(text), reason)
        # The caller keeps the fast Google translation either way. Raising with
        # the reason rather than returning a bare None is what lets the notice
        # on screen say "insufficient credits" instead of "unavailable right
        # now" — one of those an operator can act on.
        if reason:
            raise CulturalUnavailable(reason)
        return None
