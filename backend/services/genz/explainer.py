"""GenZ explanation service: RAG (KB retrieval) + LLM, with graceful fallback.

Flow:
  1. Retrieve the closest curated terms from the KB (vector search).
  2. If a confident match exists → ground the LLM in it → HIGH confidence.
  3. If not → LLM answers alone → LOW confidence, and the query is logged to the
     gap list to guide future curation (Step 5.5).
  4. If the LLM is unavailable → fall back to the curated KB row when we have one,
     otherwise a clear low-confidence "couldn't verify" answer. Never crashes.

Structured JSON is parsed defensively (same discipline as Phase 4.3) and cached.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from functools import lru_cache

import httpx

from services.genz.base import RetrievedTerm, SlangExplanation, SlangTerm
from services.genz.kb import LocalSlangKB, get_slang_kb
from services.openrouter.base import parse_llm_json
from services.translate.cache import cache_key, get_cache

logger = logging.getLogger("listenup.genz.explainer")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o"
PROMPT_VERSION = "2026-07-22.v1"
# Top combined score at/above which a KB row is trusted as grounding.
HIGH_CONFIDENCE_SCORE = 0.45

SYSTEM_PROMPT = """You explain modern internet slang, memes, and abbreviations \
to a curious adult (think a parent or teacher) who has never heard the term.

You are given VERIFIED reference entries from a curated slang database. When a \
reference matches the term in the user's message, ground your answer in it \
(keep its meaning, origin, first-seen year, and region). If nothing matches, \
answer from your own knowledge and set a humble, plain tone.

Identify the single most prominent slang term/phrase in the user's message and \
explain THAT. Keep it accurate, non-judgmental, and family-readable — briefly \
note if a term is crude or NSFW rather than being explicit.

Return ONLY this JSON (no prose, no code fences):
{{"term":"<the slang term itself>",
"plain_meaning":"<one clear sentence a grown-up understands>",
"origin":"<where it came from>",
"first_seen":"<year or era, e.g. 2020 or 'mid-2010s'>",
"region":"<where it's used, e.g. US / global, Korea>",
"example":"<one natural example sentence>",
"adult_friendly_explanation":"<2-3 sentences: what it means, the vibe, and how/when it's used>"}}

Reference entries:
{context}"""

NO_CONTEXT = "(none matched — explain from your own knowledge and stay humble)"


def _context_block(matches: list[RetrievedTerm]) -> str:
    if not matches:
        return NO_CONTEXT
    lines = []
    for m in matches:
        t = m.term
        lines.append(
            f"- {t.term}: {t.meaning} | origin: {t.origin} | first seen: {t.first_seen} "
            f"| region: {t.region} | example: {t.example}"
        )
    return "\n".join(lines)


def _from_kb(term: SlangTerm, confidence: str, model: str) -> SlangExplanation:
    return SlangExplanation(
        term=term.term,
        plain_meaning=term.meaning,
        origin=term.origin,
        first_seen=term.first_seen,
        region=term.region,
        example=term.example,
        adult_friendly_explanation=term.adult_friendly_explanation or term.meaning,
        confidence=confidence,
        grounded_terms=[term.term],
        model=model,
    )


def _coerce(
    data: dict, matches: list[RetrievedTerm], model: str, tokens: int
) -> SlangExplanation | None:
    term = data.get("term")
    meaning = data.get("plain_meaning")
    if not isinstance(term, str) or not term.strip():
        return None
    if not isinstance(meaning, str) or not meaning.strip():
        return None
    grounded = bool(matches) and matches[0].score >= HIGH_CONFIDENCE_SCORE
    return SlangExplanation(
        term=term.strip(),
        plain_meaning=meaning.strip(),
        origin=str(data.get("origin") or ""),
        first_seen=str(data.get("first_seen") or ""),
        region=str(data.get("region") or ""),
        example=str(data.get("example") or ""),
        adult_friendly_explanation=str(data.get("adult_friendly_explanation") or meaning).strip(),
        confidence="high" if grounded else "low",
        grounded_terms=[m.term.term for m in matches if m.score >= HIGH_CONFIDENCE_SCORE],
        model=model,
        tokens=tokens,
    )


class GenZExplainer(ABC):
    def __init__(self, kb: LocalSlangKB | None = None) -> None:
        self.kb = kb or get_slang_kb()

    @abstractmethod
    async def explain(self, text: str) -> SlangExplanation: ...

    def _post_search(self, text: str, result: SlangExplanation) -> None:
        """Log the query to the gap list when nothing was confidently grounded."""
        if result.confidence == "low" and not result.grounded_terms:
            self.kb.log_gap(text)


class MockGenZExplainer(GenZExplainer):
    """Deterministic, zero-cost. KB match → grounded high; else low-confidence."""

    async def explain(self, text: str) -> SlangExplanation:
        matches = self.kb.search(text)
        if matches and matches[0].score >= HIGH_CONFIDENCE_SCORE:
            result = _from_kb(matches[0].term, "high", "mock")
        else:
            result = SlangExplanation(
                term=text.strip()[:60],
                plain_meaning="This term isn't in our curated slang database yet.",
                adult_friendly_explanation=(
                    "We don't have a verified entry for this one, so we can't explain it "
                    "confidently. It may be very new, niche, or a typo."
                ),
                confidence="low",
                model="mock",
            )
        self._post_search(text, result)
        return result


class OpenRouterGenZExplainer(GenZExplainer):
    def __init__(self, kb: LocalSlangKB | None = None) -> None:
        super().__init__(kb)
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)

    async def _complete(self, text: str, context: str) -> tuple[str, int]:
        system = SYSTEM_PROMPT.format(context=context)
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
                    "temperature": 0.2,
                },
            )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        tokens = int((body.get("usage") or {}).get("total_tokens") or 0)
        return content, tokens

    async def explain(self, text: str) -> SlangExplanation:
        matches = self.kb.search(text)
        cache = get_cache()
        key = cache_key("genz", text, "explain", f"{self.model}:{PROMPT_VERSION}")
        result: SlangExplanation | None = None
        if (hit := await cache.get(key)) is not None:
            cached = SlangExplanation(**hit, cached=True, model=self.model)
            self._post_search(text, cached)
            return cached

        try:
            content, tokens = await self._complete(text, _context_block(matches))
            parsed = parse_llm_json(content)
            if parsed is not None:
                result = _coerce(parsed, matches, self.model, tokens)
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("genz_llm_failed error=%s", exc)

        if result is None:
            # LLM unusable — fall back to the curated KB row if we have one.
            if matches and matches[0].score >= HIGH_CONFIDENCE_SCORE:
                result = _from_kb(matches[0].term, "high", self.model)
            else:
                result = SlangExplanation(
                    term=text.strip()[:60],
                    plain_meaning="We couldn't verify this term right now.",
                    adult_friendly_explanation=(
                        "This term isn't in our curated database and the explainer was "
                        "unavailable, so we can't explain it confidently just now."
                    ),
                    confidence="low",
                    model=self.model,
                )
        else:
            await cache.set(key, {k: v for k, v in result.to_dict().items()
                                  if k not in ("cached", "model")})

        logger.info(
            "genz_explain term=%r confidence=%s grounded=%d tokens=%d",
            result.term, result.confidence, len(result.grounded_terms), result.tokens,
        )
        self._post_search(text, result)
        return result


@lru_cache(maxsize=1)
def get_genz_explainer() -> GenZExplainer:
    kind = os.environ.get("GENZ_EXPLAINER_SERVICE", "mock").lower()
    if kind == "real":
        return OpenRouterGenZExplainer()
    return MockGenZExplainer()
