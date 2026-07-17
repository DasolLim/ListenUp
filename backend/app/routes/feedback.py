"""Caption-quality feedback + session latency, logged for WER/latency tracking.

Phase 2 keeps this as structured logs; a later phase can persist to Supabase.
"""

import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("listenup.feedback")

router = APIRouter()


class CaptionFeedback(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    rating: Literal["up", "down"]
    final_captions: int = Field(ge=0)
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None


@router.post("/feedback/captions")
def caption_feedback(feedback: CaptionFeedback) -> dict[str, str]:
    logger.info(
        "caption_feedback session=%s rating=%s finals=%d p50_ms=%s p95_ms=%s",
        feedback.session_id,
        feedback.rating,
        feedback.final_captions,
        f"{feedback.latency_p50_ms:.0f}" if feedback.latency_p50_ms is not None else "-",
        f"{feedback.latency_p95_ms:.0f}" if feedback.latency_p95_ms is not None else "-",
    )
    return {"status": "recorded"}
