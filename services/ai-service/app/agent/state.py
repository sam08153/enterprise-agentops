from typing import Any, Dict, List, TypedDict


class AgentState(TypedDict, total=False):
    incident_id: str
    tenant_id: str
    thread_id: str

    incident: Dict[str, Any]
    logs: List[str]
    metrics: Dict[str, Any]
    deployment: Dict[str, Any]
    knowledge_results: List[Dict[str, Any]]

    findings: List[str]
    confidence: float
    final_report: Dict[str, Any]

    iteration: int
    max_iterations: int

    input_tokens: int
    output_tokens: int
    estimated_cost: float

    tool_calls: int
    tool_executions: List[Any]
