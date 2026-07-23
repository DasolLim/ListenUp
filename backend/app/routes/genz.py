"""GenZ slang explainer + curation endpoints (Phase 5).

/genz/explain       — RAG + LLM explanation of the slang in a word or phrase.
/genz/terms  (GET)  — list the curated dictionary (public).
/genz/terms  (POST) — add or update a term (auth; admin curation, Step 5.5).
/genz/gaps   (GET)  — searched-but-missing terms, the curation backlog (auth).

Slang ages fast, so curation is a first-class, ongoing path — not a one-off seed.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.supa import verify_user
from services.genz import get_genz_explainer, get_slang_kb
from services.genz.base import SlangTerm
from services.genz.kb import LocalSlangKB

logger = logging.getLogger("listenup.genz.api")

router = APIRouter(prefix="/genz")
bearer = HTTPBearer(auto_error=False)


async def require_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> str:
    if credentials is None:
        raise HTTPException(401, "Sign in to curate the slang dictionary.")
    return await verify_user(credentials.credentials)


def kb_dep() -> LocalSlangKB:
    """Indirection so tests can override the KB with an isolated instance."""
    return get_slang_kb()


class ExplainRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class TermRequest(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    meaning: str = Field(min_length=1, max_length=500)
    origin: str = Field(default="", max_length=200)
    region: str = Field(default="", max_length=120)
    first_seen: str = Field(default="", max_length=60)
    example: str = Field(default="", max_length=300)
    adult_friendly_explanation: str = Field(default="", max_length=800)


@router.post("/explain")
async def explain(request: ExplainRequest) -> dict:
    """Explain the most prominent slang term. Never errors on an unknown term —
    it returns a low-confidence answer instead (gate 5.2)."""
    service = get_genz_explainer()
    result = await service.explain(request.text.strip())
    logger.info(
        "genz_api_explain confidence=%s grounded=%d cached=%s",
        result.confidence, len(result.grounded_terms), result.cached,
    )
    return result.to_dict()


@router.get("/terms")
def list_terms(kb: Annotated[LocalSlangKB, Depends(kb_dep)]) -> list[dict]:
    return [t.to_dict() for t in kb.all_terms()]


@router.post("/terms", status_code=201)
def upsert_term(
    request: TermRequest,
    _user: Annotated[str, Depends(require_user)],
    kb: Annotated[LocalSlangKB, Depends(kb_dep)],
) -> dict:
    created = kb.add_term(SlangTerm(**request.model_dump()))
    logger.info("genz_api_ingest term=%r created=%s", request.term, created)
    return {"term": request.term, "created": created}


@router.get("/gaps")
def gaps(
    _user: Annotated[str, Depends(require_user)],
    kb: Annotated[LocalSlangKB, Depends(kb_dep)],
) -> list[dict]:
    """The curation backlog: terms users searched that we couldn't confidently explain."""
    return kb.gaps()
