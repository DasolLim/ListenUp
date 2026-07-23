"""Real OpenRouter client. Model via OPENROUTER_MODEL (env-swappable)."""

import json
import logging
import os

import httpx

from services.openrouter.base import (
    EnhancedTranslation,
    EnhancedTranslationService,
    SlangNote,
    coerce_enhanced,
    parse_llm_json,
)
from services.translate.base import SUPPORTED_LANGUAGES, assert_supported
from services.translate.cache import cache_key, get_cache

logger = logging.getLogger("listenup.openrouter")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# gpt-4o over 4o-mini: markedly better on nuanced/newer slang (e.g. "lowkey",
# ironic "coping"). Cultural accuracy is the product's core value; Redis caching
# bounds cost (repeats are free). Override with OPENROUTER_MODEL for cheaper runs.
DEFAULT_MODEL = "openai/gpt-4o"
# Bump when the prompt changes so improvements invalidate cached translations
# instead of serving stale output for up to the cache TTL.
PROMPT_VERSION = "2026-07-23.v4"

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


class OpenRouterTranslationService(EnhancedTranslationService):
    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    async def _complete(self, text: str, target_lang: str, strict_nudge: bool) -> tuple[str, int]:
        target_name = SUPPORTED_LANGUAGES.get(target_lang, target_lang)
        system = SYSTEM_PROMPT.format(target_name=target_name)
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
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.3,
                },
            )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        tokens = int((body.get("usage") or {}).get("total_tokens") or 0)
        return content, tokens

    async def translate(self, text: str, target_lang: str) -> EnhancedTranslation | None:
        assert_supported(target_lang)
        cache = get_cache()
        key = cache_key("llm", text, target_lang, f"{self.model}:{PROMPT_VERSION}")
        if (hit := await cache.get(key)) is not None:
            return EnhancedTranslation(
                translation=hit["translation"],
                register=hit["register"],
                slang_notes=[SlangNote(**n) for n in hit["slang_notes"]],
                cached=True,
                model=self.model,
            )

        # One retry with a strictness nudge — LLM JSON is never trusted blindly.
        for attempt, nudge in enumerate((False, True)):
            try:
                content, tokens = await self._complete(text, target_lang, nudge)
            except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
                logger.warning("openrouter_request_failed attempt=%d error=%s", attempt, exc)
                continue
            parsed = parse_llm_json(content)
            if parsed is None:
                logger.warning("openrouter_bad_json attempt=%d head=%r", attempt, content[:80])
                continue
            result = coerce_enhanced(parsed, self.model, tokens)
            if result is not None:
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
                    self.model, tokens, len(result.slang_notes),
                )
                return result
        logger.warning("openrouter_gave_up text_len=%d", len(text))
        return None  # caller keeps the fast Google translation
