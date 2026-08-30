from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

from app.config import settings
from app.models.incident import RCAResponse
from app.agent.graph import run_investigation_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agent", tags=["Agent"])


class InvestigateRequest(BaseModel):
    incident_id: str


@router.post("/investigate", response_model=RCAResponse)
async def investigate(request: InvestigateRequest) -> RCAResponse:
    """
    Investigate a production incident using Groq (Llama 3.1 70B).

    When MOCK_MODE=true: runs full tool loop without LLM API calls.
    When MOCK_MODE=false: calls Groq LLM with tool calling.
    """
    try:
        return run_investigation_graph(
            incident_id=request.incident_id,
            tenant_id="demo",
        )
    except Exception as e:
        logger.exception("Agent investigation failed for incident %s", request.incident_id)
        detail = str(e)
        if "GROQ_API_KEY is not configured" in detail:
            raise HTTPException(
                status_code=503,
                detail="GROQ_API_KEY is not configured. Add it to .env or set MOCK_MODE=true.",
            )
        if "LangGraph is not installed" in detail:
            raise HTTPException(status_code=503, detail=detail)
        raise HTTPException(status_code=500, detail=detail)
