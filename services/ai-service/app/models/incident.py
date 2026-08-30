from pydantic import BaseModel
from typing import Optional, List


class ToolExecutionRecord(BaseModel):
    tool_name: str
    input: str  # JSON string
    output: str  # JSON string
    status: str
    started_at: str
    completed_at: str
    duration_ms: int


class RCAResponse(BaseModel):
    incident_id: str
    service: str
    summary: str
    root_cause: str
    confidence: float
    evidence: List[str]
    recommended_actions: List[str]
    actions_executed: List[str] = []

    # Observability metadata for Java gateway
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    tool_executions: List[ToolExecutionRecord] = []
