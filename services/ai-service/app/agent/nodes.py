from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Dict

from app.agent.prompts import RCA_ANALYSIS_PROMPT_TEMPLATE
from app.agent.state import AgentState
from app.agent.tools import (
    call_tool,
    get_incident,
    get_incident_history,
    get_logs,
    get_metrics,
    get_recent_deployment,
    invoke_rca_llm,
    search_incidents,
    search_knowledge,
)


def load_incident(state: AgentState) -> dict:
    incident_id = state["incident_id"]
    tenant_id = state.get("tenant_id", "demo")
    result, record = call_tool(
        "get_incident",
        {"incident_id": incident_id, "tenant_id": tenant_id},
        get_incident,
    )
    return {
        "incident": result,
        "tool_calls": int(state.get("tool_calls", 0)) + 1,
        "tool_executions": [*state.get("tool_executions", []), record],
    }


def gather_evidence(state: AgentState) -> dict:
    incident = state.get("incident", {}) or {}
    service = incident.get("service", "unknown")
    tenant_id = state.get("tenant_id", "demo")

    def _logs():
        return call_tool("get_logs", {"service": service, "minutes": 30}, get_logs)

    def _metrics():
        return call_tool("get_metrics", {"service": service}, get_metrics)

    def _deployment():
        return call_tool("get_recent_deployment", {"service": service}, get_recent_deployment)

    def _incident_history():
        return call_tool(
            "get_incident_history",
            {"service": service, "tenant_id": tenant_id, "limit": 10},
            get_incident_history,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        logs_future = pool.submit(_logs)
        metrics_future = pool.submit(_metrics)
        deployment_future = pool.submit(_deployment)
        history_future = pool.submit(_incident_history)

        logs_result, logs_record = logs_future.result()
        metrics_result, metrics_record = metrics_future.result()
        deployment_result, deployment_record = deployment_future.result()
        history_result, history_record = history_future.result()

    tool_executions = [
        *state.get("tool_executions", []),
        logs_record,
        metrics_record,
        deployment_record,
        history_record,
    ]

    return {
        "logs": list(logs_result.get("logs", [])),
        "metrics": metrics_result,
        "deployment": deployment_result,
        "incident_history": list(history_result.get("results", [])),
        "tool_calls": int(state.get("tool_calls", 0)) + 4,
        "tool_executions": tool_executions,
    }


def research_knowledge(state: AgentState) -> dict:
    incident = state.get("incident", {}) or {}
    tenant_id = state.get("tenant_id", "demo")
    service = incident.get("service", "")
    description = incident.get("description", "")

    query = (
        "Investigate incident for service "
        f"{service}. "
        "Description:\n"
        f"{description}\n"
        "Focus on runbooks, historical incidents, and known failure modes."
    )

    def _search_knowledge():
        return call_tool(
            "search_knowledge",
            {"query": query, "tenant_id": tenant_id},
            search_knowledge,
        )

    def _search_similar_incidents():
        related_query = f"{service} {description[:200]} timeout error regression"
        return call_tool(
            "search_incidents",
            {"query": related_query, "tenant_id": tenant_id, "limit": 5},
            search_incidents,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        kf = pool.submit(_search_knowledge)
        sf = pool.submit(_search_similar_incidents)
        knowledge_result, knowledge_record = kf.result()
        similar_result, similar_record = sf.result()

    knowledge_results = list(knowledge_result.get("results", []))
    for inc in similar_result.get("results", []):
        entry = {
            "source": inc.get("incident_id", "similar-incident"),
            "type": "similar_incident",
            "title": inc.get("title", ""),
            "score": 0.75,
            "content": (
                f"Similar Historical Incident {inc.get('incident_id')}\n"
                f"Title: {inc.get('title')}\n"
                f"Severity: {inc.get('severity')}  Status: {inc.get('status')}\n"
                f"Started: {inc.get('started_at')}\n"
                f"Description: {inc.get('description', '')}"
            ),
        }
        if entry not in knowledge_results:
            knowledge_results.append(entry)

    merged = [*state.get("knowledge_results", [])]
    for r in knowledge_results:
        if r not in merged:
            merged.append(r)

    return {
        "knowledge_results": merged,
        "tool_calls": int(state.get("tool_calls", 0)) + 2,
        "tool_executions": [
            *state.get("tool_executions", []),
            knowledge_record,
            similar_record,
        ],
    }


def analyze_rca(state: AgentState) -> dict:
    prompt = RCA_ANALYSIS_PROMPT_TEMPLATE.format(
        incident=json.dumps(state.get("incident", {}), indent=2, sort_keys=True),
        logs=json.dumps(state.get("logs", []), indent=2, sort_keys=True),
        metrics=json.dumps(state.get("metrics", {}), indent=2, sort_keys=True),
        deployment=json.dumps(state.get("deployment", {}), indent=2, sort_keys=True),
        incident_history=json.dumps(state.get("incident_history", []), indent=2, sort_keys=True),
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
    incident = state.get("incident", {}) or {}

    base = (
        f"Service: {incident.get('service', '')}\n"
        f"Description: {incident.get('description', '')}\n"
        f"Deployment: {json.dumps(state.get('deployment', {}), indent=2)}\n"
    )

    findings = "\n".join(state.get("findings", [])[:3])
    query = f"{base}\nCurrent hypothesis:\n{findings}\nFind more relevant runbooks and similar incidents."

    def _search_knowledge():
        return call_tool(
            "search_knowledge",
            {"query": query, "tenant_id": tenant_id},
            search_knowledge,
        )

    def _search_similar():
        svc = incident.get("service", "")
        svc_query = f"{svc} {' '.join(state.get('findings', [])[:2])}"
        return call_tool(
            "search_incidents",
            {"query": svc_query, "tenant_id": tenant_id, "limit": 5},
            search_incidents,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        kf = pool.submit(_search_knowledge)
        sf = pool.submit(_search_similar)
        results, record = kf.result()
        sim_results, sim_record = sf.result()

    merged = [*state.get("knowledge_results", [])]
    for r in list(results.get("results", [])):
        if r not in merged:
            merged.append(r)
    for inc in sim_results.get("results", []):
        entry = {
            "source": inc.get("incident_id", "similar-incident"),
            "type": "similar_incident",
            "title": inc.get("title", ""),
            "score": 0.75,
            "content": (
                f"Similar Historical Incident {inc.get('incident_id')}\n"
                f"Title: {inc.get('title')}\n"
                f"Severity: {inc.get('severity')}\n"
                f"Description: {inc.get('description', '')}"
            ),
        }
        if entry not in merged:
            merged.append(entry)

    return {
        "iteration": iteration,
        "knowledge_results": merged,
        "tool_calls": int(state.get("tool_calls", 0)) + 2,
        "tool_executions": [
            *state.get("tool_executions", []),
            record,
            sim_record,
        ],
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
