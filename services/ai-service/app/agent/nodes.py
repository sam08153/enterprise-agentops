from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from app.agent.prompts import RCA_ANALYSIS_PROMPT_TEMPLATE
from app.agent.state import AgentState
from app.agent.tools import (
    call_tool,
    get_incident,
    get_logs,
    get_metrics,
    get_recent_deployment,
    invoke_rca_llm,
    search_knowledge,
)


def load_incident(state: AgentState) -> dict:
    incident_id = state["incident_id"]
    result, record = call_tool("get_incident", {"incident_id": incident_id}, get_incident)
    return {
        "incident": result,
        "tool_calls": int(state.get("tool_calls", 0)) + 1,
        "tool_executions": [*state.get("tool_executions", []), record],
    }


def gather_evidence(state: AgentState) -> dict:
    service = state["incident"]["service"]

    def _logs():
        return call_tool("get_logs", {"service": service, "minutes": 30}, get_logs)

    def _metrics():
        return call_tool("get_metrics", {"service": service}, get_metrics)

    def _deployment():
        return call_tool("get_recent_deployment", {"service": service}, get_recent_deployment)

    with ThreadPoolExecutor(max_workers=3) as pool:
        logs_future = pool.submit(_logs)
        metrics_future = pool.submit(_metrics)
        deployment_future = pool.submit(_deployment)

        logs_result, logs_record = logs_future.result()
        metrics_result, metrics_record = metrics_future.result()
        deployment_result, deployment_record = deployment_future.result()

    tool_executions = [
        *state.get("tool_executions", []),
        logs_record,
        metrics_record,
        deployment_record,
    ]

    return {
        "logs": list(logs_result.get("logs", [])),
        "metrics": metrics_result,
        "deployment": deployment_result,
        "tool_calls": int(state.get("tool_calls", 0)) + 3,
        "tool_executions": tool_executions,
    }


def research_knowledge(state: AgentState) -> dict:
    incident = state["incident"]
    query = (
        "Investigate incident for service "
        f"{incident.get('service', '')}. "
        "Description:\n"
        f"{incident.get('description', '')}\n"
        "Focus on runbooks, historical incidents, and known failure modes."
    )

    tenant_id = state.get("tenant_id", "demo")
    results, record = call_tool(
        "search_knowledge",
        {"query": query, "tenant_id": tenant_id},
        search_knowledge,
    )

    return {
        "knowledge_results": list(results.get("results", [])),
        "tool_calls": int(state.get("tool_calls", 0)) + 1,
        "tool_executions": [*state.get("tool_executions", []), record],
    }


def analyze_rca(state: AgentState) -> dict:
    prompt = RCA_ANALYSIS_PROMPT_TEMPLATE.format(
        incident=json.dumps(state.get("incident", {}), indent=2, sort_keys=True),
        logs=json.dumps(state.get("logs", []), indent=2, sort_keys=True),
        metrics=json.dumps(state.get("metrics", {}), indent=2, sort_keys=True),
        deployment=json.dumps(state.get("deployment", {}), indent=2, sort_keys=True),
        knowledge_results=json.dumps(state.get("knowledge_results", []), indent=2, sort_keys=True),
    )

    parsed, input_tokens, output_tokens = invoke_rca_llm(prompt)

    confidence = float(parsed.get("confidence", 0.0) or 0.0)
    findings = []
    if parsed.get("root_cause"):
        findings.append(str(parsed["root_cause"]))

    final_report: Dict = {
        "summary": parsed.get("summary", ""),
        "root_cause": parsed.get("root_cause", ""),
        "confidence": confidence,
        "evidence": list(parsed.get("evidence", []) or []),
        "recommended_actions": list(parsed.get("recommended_actions", []) or []),
        "alternative_causes": list(parsed.get("alternative_causes", []) or []),
    }

    return {
        "findings": findings,
        "confidence": confidence,
        "final_report": final_report,
        "input_tokens": int(state.get("input_tokens", 0)) + int(input_tokens),
        "output_tokens": int(state.get("output_tokens", 0)) + int(output_tokens),
    }


def research_more(state: AgentState) -> dict:
    iteration = int(state.get("iteration", 0)) + 1
    tenant_id = state.get("tenant_id", "demo")
    incident = state.get("incident", {})

    base = (
        f"Service: {incident.get('service', '')}\n"
        f"Description: {incident.get('description', '')}\n"
        f"Deployment: {json.dumps(state.get('deployment', {}), indent=2)}\n"
    )

    findings = "\n".join(state.get("findings", [])[:3])
    query = f"{base}\nCurrent hypothesis:\n{findings}\nFind more relevant runbooks and similar incidents."

    results, record = call_tool(
        "search_knowledge",
        {"query": query, "tenant_id": tenant_id},
        search_knowledge,
    )

    merged = [*state.get("knowledge_results", [])]
    for r in list(results.get("results", [])):
        if r not in merged:
            merged.append(r)

    return {
        "iteration": iteration,
        "knowledge_results": merged,
        "tool_calls": int(state.get("tool_calls", 0)) + 1,
        "tool_executions": [*state.get("tool_executions", []), record],
    }


def route_after_analysis(state: AgentState) -> str:
    confidence = float(state.get("confidence", 0.0) or 0.0)
    iteration = int(state.get("iteration", 0) or 0)
    max_iterations = int(state.get("max_iterations", 5) or 5)

    if confidence >= 0.80:
        return "finalize"

    if iteration >= max_iterations:
        return "finalize"

    return "research_more"


def finalize(state: AgentState) -> dict:
    report = dict(state.get("final_report", {}) or {})
    report.setdefault("confidence", float(state.get("confidence", 0.0) or 0.0))
    return {"final_report": report}
