"""Translation endpoints. General = Google v3 (fast, cached). The enhanced
(cultural) endpoint arrives in Step 4.3."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.plans import ENHANCED_COST_RATIO
from app.routes.billing import Caller, requires
from services.openrouter import get_enhanced_translation_service
from services.translate import TranslationError, get_translation_service
from services.translate.base import SUPPORTED_LANGUAGES
from services.translate.cache import get_cache

logger = logging.getLogger("listenup.translate.api")

router = APIRouter(prefix="/translate")


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    target_lang: str
    source_lang: str | None = None


@router.get("/languages")
def languages() -> dict[str, str]:
    return SUPPORTED_LANGUAGES


@router.post("")
async def translate(
    request: TranslateRequest,
    who: Annotated[Caller, Depends(requires("translated"))],
) -> dict:
    # Same-language request: return the text untouched rather than paying a
    # provider to echo it. Users hit this whenever the target still matches the
    # language they typed, and a "translation" identical to the input reads as a
    # broken tool.
    if request.source_lang and request.source_lang == request.target_lang:
        return {
            "translation": request.text,
            "detectedSourceLang": request.source_lang,
            "cached": True,
            "characters": 0,
            "unchanged": True,
        }

    service = get_translation_service()
    try:
        result = await service.translate(
            request.text, request.target_lang, request.source_lang
        )
    except TranslationError as exc:
        raise HTTPException(400, str(exc)) from exc
    cache = get_cache()
    # Meter what we actually spend. `characters` is 0 on a cache hit, so a
    # repeated phrase costs the provider nothing and costs the user nothing off
    # their allowance either — the cap tracks margin rather than punishing
    # someone for a conversation that happens to repeat itself.
    await who.record("translated", result.characters)
    logger.info(
        "translate chars=%d cached=%s hit_ratio=%.2f",
        result.characters, result.cached, cache.hit_ratio,
    )
    return {
        "translation": result.text,
        "detectedSourceLang": result.detected_source_lang,
        "cached": result.cached,
        "characters": result.characters,
    }


@router.post("/enhanced")
async def translate_enhanced(
    request: TranslateRequest,
    who: Annotated[Caller, Depends(requires("translated"))],
) -> dict:
    """Cultural layer: register + slang notes. 502 (not a crash) when the LLM
    can't produce usable JSON — the client keeps the fast translation."""
    service = get_enhanced_translation_service()
    try:
        result = await service.translate(request.text, request.target_lang)
    except TranslationError as exc:
        raise HTTPException(400, str(exc)) from exc
    if result is None:
        raise HTTPException(
            502, "Cultural notes are unavailable right now; the fast translation stands."
        )
    # Weighted at the cultural pass's real share of cost, not at full character
    # value — see ENHANCED_COST_RATIO. Cached results cost nothing and meter
    # nothing.
    if not result.cached:
        await who.record("translated", round(len(request.text) * ENHANCED_COST_RATIO))
    logger.info(
        "translate_enhanced model=%s tokens=%d cached=%s notes=%d",
        result.model, result.tokens, result.cached, len(result.slang_notes),
    )
    return {
        "translation": result.translation,
        "register": result.register,
        "slangNotes": [note.__dict__ for note in result.slang_notes],
        "cached": result.cached,
        "model": result.model,
        "tokens": result.tokens,
    }


@router.get("/stats")
def stats() -> dict:
    cache = get_cache()
    return {"hits": cache.hits, "misses": cache.misses, "hitRatio": round(cache.hit_ratio, 3)}
