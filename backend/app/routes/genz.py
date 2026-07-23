"""GenZ slang explainer endpoints (Phase 5).

/genz/explain  — RAG + LLM explanation of the slang in a word or phrase.
Curation endpoints (/genz/terms, /genz/gaps) are added in Step 5.5.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services.genz import get_genz_explainer

logger = logging.getLogger("listenup.genz.api")

router = APIRouter(prefix="/genz")


class ExplainRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)


@router.post("/explain")
async def explain(request: ExplainRequest) -> dict:
    """Explain the most prominent slang term in the input. Never errors on an
    unknown term — it returns a low-confidence answer instead (gate 5.2)."""
    service = get_genz_explainer()
    result = await service.explain(request.text.strip())
    logger.info(
        "genz_api_explain confidence=%s grounded=%d cached=%s",
        result.confidence, len(result.grounded_terms), result.cached,
    )
    return result.to_dict()
