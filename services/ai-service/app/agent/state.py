from typing import Any, Dict, List, TypedDict


class EvidenceRecord(TypedDict, total=False):
    source_type: str
    source: str
    reference: str
    claim: str
    confidence: str
    reliability: str


class AgentState(TypedDict, total=False):
    incident_id: str
    tenant_id: str
    thread_id: str

    incident: Dict[str, Any]
    logs: List[Any]
    metrics: Dict[str, Any]
    deployment: Dict[str, Any]
    health: Dict[str, Any]

    commits: List[Any]
    pull_request: Dict[str, Any]
    code_search: List[Any]
    code_files: List[Any]

    incident_history: List[Dict[str, Any]]
    knowledge_results: List[Dict[str, Any]]

    evidence: List[EvidenceRecord]

    findings: List[str]
    confidence: float
    final_report: Dict[str, Any]

    iteration: int
    max_iterations: int

    input_tokens: int
    output_tokens: int
    estimated_cost: float

    tool_calls: int
    max_tool_calls: int
    tool_executions: List[Any]

    tool_failures: Dict[str, int]
    open_circuits: List[str]
