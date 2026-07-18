"""Translation endpoints. General = Google v3 (fast, cached). The enhanced
(cultural) endpoint arrives in Step 4.3."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
async def translate(request: TranslateRequest) -> dict:
    service = get_translation_service()
    try:
        result = await service.translate(
            request.text, request.target_lang, request.source_lang
        )
    except TranslationError as exc:
        raise HTTPException(400, str(exc)) from exc
    cache = get_cache()
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


@router.get("/stats")
def stats() -> dict:
    cache = get_cache()
    return {"hits": cache.hits, "misses": cache.misses, "hitRatio": round(cache.hit_ratio, 3)}
