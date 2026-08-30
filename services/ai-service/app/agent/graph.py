from __future__ import annotations

from typing import Any, Dict

from app.agent.state import AgentState
from app.models.incident import RCAResponse


def build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception as e:
        raise RuntimeError(
            "LangGraph is not installed. Add langgraph to requirements and install dependencies."
        ) from e

    from app.agent import nodes

    graph = StateGraph(AgentState)

    graph.add_node("load_incident", nodes.load_incident)
    graph.add_node("gather_evidence", nodes.gather_evidence)
    graph.add_node("research_knowledge", nodes.research_knowledge)
    graph.add_node("analyze_rca", nodes.analyze_rca)
    graph.add_node("research_more", nodes.research_more)
    graph.add_node("finalize", nodes.finalize)

    graph.add_edge(START, "load_incident")
    graph.add_edge("load_incident", "gather_evidence")
    graph.add_edge("gather_evidence", "research_knowledge")
    graph.add_edge("research_knowledge", "analyze_rca")

    graph.add_conditional_edges(
        "analyze_rca",
        nodes.route_after_analysis,
        {
            "finalize": "finalize",
            "research_more": "research_more",
        },
    )

    graph.add_edge("research_more", "analyze_rca")
    graph.add_edge("finalize", END)

    compiled = _compile_with_checkpointer(graph)
    return compiled


def _compile_with_checkpointer(graph):
    try:
        from langgraph.checkpoint.memory import MemorySaver
    except Exception:
        MemorySaver = None

    if MemorySaver is None:
        return graph.compile()

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


def run_investigation_graph(
    incident_id: str,
    tenant_id: str = "demo",
    thread_id: str | None = None,
    max_iterations: int = 5,
) -> RCAResponse:
    graph = build_graph()

    thread_id = thread_id or f"incident-{incident_id}-run-001"
    initial_state: AgentState = {
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "thread_id": thread_id,
        "iteration": 0,
        "max_iterations": max_iterations,
        "incident_history": [],
        "knowledge_results": [],
        "findings": [],
        "confidence": 0.0,
        "final_report": {},
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0.0,
        "tool_calls": 0,
        "tool_executions": [],
    }

    config: Dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    final_state = graph.invoke(initial_state, config=config)

    report = dict(final_state.get("final_report", {}) or {})
    confidence = float(final_state.get("confidence", report.get("confidence", 0.0)) or 0.0)

    incident = final_state.get("incident", {}) or {}
    service = str(incident.get("service", "unknown") or "unknown")

    return RCAResponse(
        incident_id=incident_id,
        service=service,
        summary=str(report.get("summary", "") or ""),
        root_cause=str(report.get("root_cause", "") or ""),
        confidence=confidence,
        evidence=list(report.get("evidence", []) or []),
        recommended_actions=list(report.get("recommended_actions", []) or []),
        actions_executed=[],
        input_tokens=int(final_state.get("input_tokens", 0) or 0),
        output_tokens=int(final_state.get("output_tokens", 0) or 0),
        tool_calls=int(final_state.get("tool_calls", 0) or 0),
        tool_executions=list(final_state.get("tool_executions", []) or []),
    )

