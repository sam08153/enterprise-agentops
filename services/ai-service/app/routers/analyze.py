from fastapi import APIRouter
from app.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter(prefix="/api/v1", tags=["Analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_incident(request: AnalyzeRequest) -> AnalyzeResponse:
    """
    Analyze an incident.
    Phase 1: Stub — intelligent analysis will be implemented in the next phase.
    """
    return AnalyzeResponse(
        status="RECEIVED",
        message="Incident analysis will be implemented in the next phase.",
    )
