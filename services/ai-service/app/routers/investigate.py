from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import groq
import logging

from app.agent.agent import run_investigation
from app.agent.mock_agent import run_mock_investigation
from app.config import settings
from app.models.incident import RCAResponse

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
    if settings.mock_mode:
        logger.info("[MOCK MODE] Running mock investigation for %s", request.incident_id)
        return run_mock_investigation(request.incident_id)

    if not settings.groq_api_key:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not configured. Add it to .env or set MOCK_MODE=true.",
        )
    try:
        client = groq.Groq(api_key=settings.groq_api_key)
        result = run_investigation(request.incident_id, client)
        return result
    except groq.AuthenticationError:
        raise HTTPException(
            status_code=401,
            detail="Groq API key is invalid. Check GROQ_API_KEY in .env.",
        )
    except Exception as e:
        logger.exception("Agent investigation failed for incident %s", request.incident_id)
        raise HTTPException(status_code=500, detail=str(e))
