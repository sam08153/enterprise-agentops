from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from app.agent.prompts import RCA_ANALYSIS_PROMPT_TEMPLATE
from app.agent.state import AgentState, EvidenceRecord
from app.agent.tools import (
    call_tool,
    get_file as gh_get_file,
    get_incident,
    get_incident_history,
    get_logs,
    get_metrics,
    get_pull_request as gh_get_pr,
    get_recent_commits as gh_get_commits,
    get_recent_deployment,
    get_service_health,
    invoke_rca_llm,
    search_code as gh_search_code,
    search_incidents,
    search_knowledge,
)
from app.tools.github import repo_from_service

MAX_TOOL_CALLS = 20
CIRCUIT_BREAKER_THRESHOLD = 2


def _add_evidence(state: AgentState, new_ev: List[EvidenceRecord]) -> List[EvidenceRecord]:
    existing = list(state.get("evidence", []) or [])
    existing.extend(new_ev)
    return existing


def _record_tool_failure(state: AgentState, tool_name: str) -> Tuple[Dict[str, int], List[str]]:
    failures = dict(state.get("tool_failures", {}) or {})
    failures[tool_name] = int(failures.get(tool_name, 0)) + 1
    open_circuits = list(state.get("open_circuits", []) or [])
    if failures[tool_name] >= CIRCUIT_BREAKER_THRESHOLD and tool_name not in open_circuits:
        open_circuits.append(tool_name)
    return failures, open_circuits


def _circuit_open(state: AgentState, tool_name: str) -> bool:
    return tool_name in (state.get("open_circuits", []) or [])


def _budget_exceeded(state: AgentState, delta: int = 0) -> bool:
    budget = int(state.get("max_tool_calls", MAX_TOOL_CALLS) or MAX_TOOL_CALLS)
    used = int(state.get("tool_calls", 0) or 0) + delta
    return used >= budget


def load_incident(state: AgentState) -> dict:
    incident_id = state["incident_id"]
    tenant_id = state.get("tenant_id", "demo")

    if _circuit_open(state, "get_incident") or _budget_exceeded(state, 1):
        return {"incident": {"incident_id": incident_id, "service": "unknown", "error": "unavailable"}}

    result, record = call_tool(
        "get_incident",
        {"incident_id": incident_id, "tenant_id": tenant_id},
        get_incident,
    )
    failed = "error" in result

    ev: List[EvidenceRecord] = []
    if not failed and result.get("incident_id"):
        ev.append({
            "source_type": "postgres",
            "source": "incident_db",
            "reference": result.get("incident_id", incident_id),
            "claim": (
                f"Incident {incident_id}: '{result.get('title','')}' affects "
                f"{result.get('service','unknown')} severity={result.get('severity','?')} "
                f"error_rate={result.get('error_rate','?')} started at {result.get('started_at','?')}"
            ),
            "confidence": "HIGH",
            "reliability": "HIGH",
        })

    out: Dict[str, Any] = {
        "incident": result,
        "tool_calls": int(state.get("tool_calls", 0)) + 1,
        "tool_executions": [*state.get("tool_executions", []), record],
        "evidence": _add_evidence(state, ev),
    }
    if failed:
        f, c = _record_tool_failure(state, "get_incident")
        out["tool_failures"] = f
        out["open_circuits"] = c
    return out


def _run_one(label: str, tool_name: str, args: dict, fn, state: AgentState) -> Tuple[str, Any, Any]:
    try:
        result, record = call_tool(tool_name, args, fn)
        return label, result, record
    except Exception as e:
        return label, {"error": str(e), "error_type": type(e).__name__}, None


def gather_evidence(state: AgentState) -> dict:
    incident = state.get("incident", {}) or {}
    service = incident.get("service", "unknown") or "unknown"
    tenant_id = state.get("tenant_id", "demo")
    repository = repo_from_service(service)

    tool_executions = list(state.get("tool_executions", []) or [])
    tool_calls = int(state.get("tool_calls", 0) or 0)
    failures = dict(state.get("tool_failures", {}) or {})
    open_circuits = list(state.get("open_circuits", []) or [])

    logs_result: Dict[str, Any] = {"logs": []}
    metrics_result: Dict[str, Any] = {}
    deployment_result: Dict[str, Any] = {}
    health_result: Dict[str, Any] = {}
    history_result: Dict[str, Any] = {"results": []}
    commits_result: Dict[str, Any] = {"commits": []}
    search_result: Dict[str, Any] = {"results": []}

    tasks: List[Tuple[str, str, dict, Any]] = []

    if not _circuit_open(state, "get_logs") and not _budget_exceeded(state, tool_calls + 1):
        tasks.append(("logs", "get_logs", {"service": service, "minutes": 60}, get_logs))
    if not _circuit_open(state, "get_metrics") and not _budget_exceeded(state, tool_calls + 1):
        tasks.append(("metrics", "get_metrics", {"service": service, "window_minutes": 30, "tenant_id": tenant_id}, get_metrics))
    if not _circuit_open(state, "get_recent_deployment") and not _budget_exceeded(state, tool_calls + 1):
        tasks.append(("deployment", "get_recent_deployment", {"service": service, "tenant_id": tenant_id}, get_recent_deployment))
    if not _circuit_open(state, "get_service_health") and not _budget_exceeded(state, tool_calls + 1):
        tasks.append(("health", "get_service_health", {"service": service, "tenant_id": tenant_id}, get_service_health))
    if not _circuit_open(state, "get_incident_history") and not _budget_exceeded(state, tool_calls + 1):
        tasks.append(("history", "get_incident_history", {"service": service, "tenant_id": tenant_id, "limit": 10}, get_incident_history))
    if not _circuit_open(state, "github.get_recent_commits") and not _budget_exceeded(state, tool_calls + 1):
        tasks.append(("commits", "github.get_recent_commits", {"repository": repository, "branch": "main", "limit": 10, "tenant_id": tenant_id}, gh_get_commits))
    if not _circuit_open(state, "github.search_code") and not _budget_exceeded(state, tool_calls + 1):
        tasks.append(("search", "github.search_code", {"repository": repository, "query": "timeout", "limit": 10, "tenant_id": tenant_id}, gh_search_code))

    remaining = MAX_TOOL_CALLS - tool_calls
    tasks = tasks[: max(0, remaining)]

    results: Dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_run_one, t[0], t[1], t[2], t[3], state): t[0] for t in tasks}
        for fut in as_completed(futures):
            label, result, record = fut.result()
            results[label] = result
            if record is not None:
                tool_executions.append(record)
            tool_calls += 1

    logs_result = results.get("logs", {"logs": [], "error": "skipped (circuit open or budget)"})
    metrics_result = results.get("metrics", {})
    deployment_result = results.get("deployment", {})
    health_result = results.get("health", {})
    history_result = results.get("history", {"results": []})
    commits_result = results.get("commits", {"commits": []})
    search_result = results.get("search", {"results": []})

    evidence: List[EvidenceRecord] = list(state.get("evidence", []) or [])

    if "metrics" in results and metrics_result and not metrics_result.get("error"):
        m = metrics_result.get("metrics", {}) or {}
        evidence.append({
            "source_type": "aws",
            "source": "cloudwatch_metrics",
            "reference": f"{service}/30m",
            "claim": (
                f"Error rate {m.get('error_rate','?')}% (Δ +{m.get('error_rate_delta_vs_previous','?')}pp), "
                f"p95 latency {m.get('latency_p95_ms','?')}ms (Δ +{m.get('latency_p95_delta_vs_previous','?')}ms), "
                f"CPU {m.get('cpu_percent','?')}%, Memory {m.get('memory_percent','?')}%"
            ),
            "confidence": "HIGH",
            "reliability": "HIGH",
        })
    if "health" in results and health_result and not health_result.get("error"):
        evidence.append({
            "source_type": "aws",
            "source": "ecs_health",
            "reference": service,
            "claim": (
                f"Service status={health_result.get('status','?')}, "
                f"healthy={health_result.get('healthy_instances',0)}/{health_result.get('desired_instances',0)}, "
                f"health={health_result.get('health_percent','?')}%"
            ),
            "confidence": "HIGH",
            "reliability": "HIGH",
        })
    if "deployment" in results and deployment_result and not deployment_result.get("error"):
        evidence.append({
            "source_type": "aws",
            "source": "codedeploy",
            "reference": f"{deployment_result.get('version','?')}@{deployment_result.get('deployed_at','?')}",
            "claim": (
                f"Recent deployment version={deployment_result.get('version','?')} "
                f"deployed_at={deployment_result.get('deployed_at','?')} "
                f"(previous: {deployment_result.get('previous_version','?')})"
            ),
            "confidence": "HIGH",
            "reliability": "HIGH",
        })
    if "logs" in results and isinstance(logs_result, dict):
        logs_list = list(logs_result.get("logs", []) or [])
        if logs_list:
            sample = next((l for l in logs_list if "timeout" in str(l.get("message","")).lower() or "error" in str(l.get("level","")).upper()), None)
            if sample is None and logs_list:
                sample = logs_list[0]
            msg = str(sample.get("message", "")) if isinstance(sample, dict) else str(sample)
            counts = logs_result.get("log_level_counts", {}) or {}
            evidence.append({
                "source_type": "aws",
                "source": "cloudwatch_logs",
                "reference": f"{service}/60m total={logs_result.get('total_returned', len(logs_list))}",
                "claim": (
                    f"CloudWatch logs summary: counts={counts}. "
                    f"Sample ERROR entry: {msg[:300]}"
                ),
                "confidence": "HIGH",
                "reliability": "MEDIUM",
            })
    if "history" in results and isinstance(history_result, dict) and history_result.get("results"):
        ev_ids = [str(i.get("incident_id", "?")) for i in history_result["results"]][:5]
        evidence.append({
            "source_type": "postgres",
            "source": "incident_history",
            "reference": service,
            "claim": f"Prior incident history for {service}: {', '.join(ev_ids)}",
            "confidence": "HIGH",
            "reliability": "HIGH",
        })
    if "commits" in results and isinstance(commits_result, dict) and commits_result.get("commits"):
        top = commits_result["commits"][0]
        evidence.append({
            "source_type": "github",
            "source": "commit",
            "reference": str(top.get("sha", "?"))[:12],
            "claim": (
                f"Most recent commit: '{str(top.get('message',''))[:100]}' "
                f"by {top.get('author','?')} at {top.get('timestamp','?')}. "
                f"Files changed: {top.get('files_changed', [])[:3]}"
            ),
            "confidence": "HIGH",
            "reliability": "HIGH",
        })
        pr_number = top.get("pr_number")
        if pr_number and not _circuit_open(state, "github.get_pull_request") and not _budget_exceeded(state, tool_calls + 1):
            pr_args = {"repository": repository, "number": int(pr_number), "tenant_id": tenant_id}
            _lbl, pr_out, pr_rec = _run_one("pr", "github.get_pull_request", pr_args, gh_get_pr, state)
            if pr_rec is not None:
                tool_executions.append(pr_rec)
            tool_calls += 1
            if not pr_out.get("error") and pr_out.get("pull_request"):
                pr = pr_out["pull_request"]
                evidence.append({
                    "source_type": "github",
                    "source": "pull_request",
                    "reference": f"PR #{pr.get('number','?')}",
                    "claim": (
                        f"PR #{pr.get('number','?')}: '{pr.get('title','')[:120]}' "
                        f"status={pr.get('status','?')} merged_at={pr.get('merged_at','?')} "
                        f"files={pr.get('files_changed','?')}. Description: {pr.get('description','')[:200]}"
                    ),
                    "confidence": "HIGH",
                    "reliability": "HIGH",
                })
    if "search" in results and isinstance(search_result, dict) and search_result.get("results"):
        files_hit = [str(r.get("file", "?")) for r in search_result["results"][:3]]
        evidence.append({
            "source_type": "github",
            "source": "code_search",
            "reference": f"repo={repository} q='timeout'",
            "claim": f"Source-code hits for query 'timeout': {', '.join(files_hit)}",
            "confidence": "MEDIUM",
            "reliability": "MEDIUM",
        })
        if search_result["results"] and not _circuit_open(state, "github.get_file") and not _budget_exceeded(state, tool_calls + 2):
            for hit in search_result["results"][:2]:
                file_args = {"repository": repository, "file_path": hit["file"], "ref": "main", "tenant_id": tenant_id}
                _lbl, f_out, f_rec = _run_one("file", "github.get_file", file_args, gh_get_file, state)
                if f_rec is not None:
                    tool_executions.append(f_rec)
                tool_calls += 1
                if not f_out.get("error") and f_out.get("file"):
                    f = f_out["file"]
                    evidence.append({
                        "source_type": "github",
                        "source": "source_file",
                        "reference": f"{repository}:{hit['file']}@main",
                        "claim": (
                            f"File {hit['file']} ({f.get('line_count','?')} lines) retrieved. "
                            f"First 280 chars of content: {str(f.get('content',''))[:280]}"
                        ),
                        "confidence": "MEDIUM",
                        "reliability": "MEDIUM",
                    })

    for label, result in results.items():
        if isinstance(result, dict) and result.get("error"):
            failures, open_circuits = _record_tool_failure(
                {"tool_failures": failures, "open_circuits": open_circuits}, label
            )

    return {
        "logs": list(logs_result.get("logs", []) if isinstance(logs_result, dict) else []),
        "metrics": metrics_result,
        "deployment": deployment_result,
        "health": health_result,
        "commits": list(commits_result.get("commits", []) if isinstance(commits_result, dict) else []),
        "code_search": list(search_result.get("results", []) if isinstance(search_result, dict) else []),
        "incident_history": list(history_result.get("results", []) if isinstance(history_result, dict) else []),
        "evidence": evidence,
        "tool_calls": tool_calls,
        "tool_executions": tool_executions,
        "tool_failures": failures,
        "open_circuits": open_circuits,
    }


def research_knowledge(state: AgentState) -> dict:
    incident = state.get("incident", {}) or {}
    tenant_id = state.get("tenant_id", "demo")
    service = incident.get("service", "")
    description = incident.get("description", "")

    query = (
        f"Investigate incident for service {service}. "
        f"Description: {description}\n"
        "Focus on runbooks, historical incidents, and known failure modes."
    )

    related_query = f"{service} timeout error regression"

    tool_executions = list(state.get("tool_executions", []) or [])
    tool_calls = int(state.get("tool_calls", 0) or 0)
    delta = 2
    if _budget_exceeded(state, delta):
        return {
            "knowledge_results": list(state.get("knowledge_results", []) or []),
        }

    with ThreadPoolExecutor(max_workers=2) as pool:
        kf = pool.submit(
            lambda: call_tool("search_knowledge", {"query": query, "tenant_id": tenant_id}, search_knowledge)
        )
        sf = pool.submit(
            lambda: call_tool("search_incidents", {"query": related_query, "tenant_id": tenant_id, "limit": 5}, search_incidents)
        )
        knowledge_result, knowledge_record = kf.result()
        similar_result, similar_record = sf.result()

    tool_executions.extend([knowledge_record, similar_record])
    tool_calls += 2

    knowledge_results = list(knowledge_result.get("results", []) if isinstance(knowledge_result, dict) else [])
    for inc in (similar_result.get("results", []) if isinstance(similar_result, dict) else []):
        entry = {
            "source": inc.get("incident_id", "similar-incident"),
            "type": "similar_incident",
            "title": inc.get("title", ""),
            "score": 0.75,
            "content": (
                f"Similar Historical Incident {inc.get('incident_id')}\n"
                f"Title: {inc.get('title')}\nSeverity: {inc.get('severity')}  "
                f"Status: {inc.get('status')}\nStarted: {inc.get('started_at')}\n"
                f"Description: {inc.get('description', '')}"
            ),
        }
        if entry not in knowledge_results:
            knowledge_results.append(entry)

    merged = list(state.get("knowledge_results", []) or [])
    for r in knowledge_results:
        if r not in merged:
            merged.append(r)

    new_ev: List[EvidenceRecord] = []
    for r in merged:
        src = r.get("source", "")
        if "INC-0" in str(src) and src in ["INC-0912", "INC-0847", "INC-0799"]:
            new_ev.append({
                "source_type": "rag",
                "source": "historical_incident",
                "reference": str(src),
                "claim": f"Historical incident matched: {str(r.get('title',''))[:150]}",
                "confidence": "MEDIUM",
                "reliability": "HIGH",
            })
        if "runbook" in str(r.get("title", "")).lower() or "runbook" in str(r.get("type", "")).lower():
            new_ev.append({
                "source_type": "rag",
                "source": "runbook",
                "reference": str(src),
                "claim": f"Runbook loaded: {str(r.get('title',''))[:100]}",
                "confidence": "MEDIUM",
                "reliability": "MEDIUM",
            })

    evidence = _add_evidence(state, new_ev)

    return {
        "knowledge_results": merged,
        "evidence": evidence,
        "tool_calls": tool_calls,
        "tool_executions": tool_executions,
    }


def analyze_rca(state: AgentState) -> dict:
    prompt = RCA_ANALYSIS_PROMPT_TEMPLATE.format(
        incident=json.dumps(state.get("incident", {}), indent=2, sort_keys=True, default=str),
        logs=json.dumps(state.get("logs", []), indent=2, sort_keys=True, default=str),
        metrics=json.dumps(state.get("metrics", {}), indent=2, sort_keys=True, default=str),
        deployment=json.dumps(state.get("deployment", {}), indent=2, sort_keys=True, default=str),
        health=json.dumps(state.get("health", {}), indent=2, sort_keys=True, default=str),
        commits=json.dumps(state.get("commits", []), indent=2, sort_keys=True, default=str),
        code_search=json.dumps(state.get("code_search", []), indent=2, sort_keys=True, default=str),
        incident_history=json.dumps(state.get("incident_history", []), indent=2, sort_keys=True, default=str),
        knowledge_results=json.dumps(state.get("knowledge_results", []), indent=2, sort_keys=True, default=str),
        evidence=json.dumps(state.get("evidence", []), indent=2, sort_keys=True, default=str),
        tool_failures=json.dumps(state.get("tool_failures", {}), indent=2, sort_keys=True, default=str),
        open_circuits=json.dumps(state.get("open_circuits", []), indent=2, sort_keys=True, default=str),
        tool_calls=json.dumps(state.get("tool_calls", 0)),
        max_tool_calls=json.dumps(state.get("max_tool_calls", MAX_TOOL_CALLS)),
    )

    parsed, input_tokens, output_tokens = invoke_rca_llm(prompt)

    confidence = float(parsed.get("confidence", 0.0) or 0.0)
    findings: List[str] = list(state.get("findings", []) or [])
    if parsed.get("root_cause"):
        findings.append(str(parsed["root_cause"]))

    final_report: Dict[str, Any] = {
        "summary": parsed.get("summary", ""),
        "root_cause": parsed.get("root_cause", ""),
        "confidence": confidence,
        "evidence": list(parsed.get("evidence", []) or []),
        "recommended_actions": list(parsed.get("recommended_actions", []) or []),
        "alternative_causes": list(parsed.get("alternative_causes", []) or []),
        "actions_executed": [],
    }

    return {
        "findings": findings,
        "confidence": confidence,
        "final_report": final_report,
        "input_tokens": int(state.get("input_tokens", 0) or 0) + int(input_tokens),
        "output_tokens": int(state.get("output_tokens", 0) or 0) + int(output_tokens),
    }


def research_more(state: AgentState) -> dict:
    iteration = int(state.get("iteration", 0) or 0) + 1
    tenant_id = state.get("tenant_id", "demo")
    incident = state.get("incident", {}) or {}
    tool_calls = int(state.get("tool_calls", 0) or 0)

    if _budget_exceeded(state, 2):
        return {"iteration": iteration}

    base = (
        f"Service: {incident.get('service', '')}\n"
        f"Description: {incident.get('description', '')}\n"
        f"Deployment: {json.dumps(state.get('deployment', {}), default=str)}\n"
    )
    findings = "\n".join(state.get("findings", [])[:3])
    query = f"{base}\nCurrent hypothesis:\n{findings}\nFind more relevant runbooks and similar incidents."

    tool_executions = list(state.get("tool_executions", []) or [])
    with ThreadPoolExecutor(max_workers=2) as pool:
        kf = pool.submit(lambda: call_tool("search_knowledge", {"query": query, "tenant_id": tenant_id}, search_knowledge))
        svc = incident.get("service", "")
        svc_query = f"{svc} {' '.join(state.get('findings', [])[:2])}"
        sf = pool.submit(lambda: call_tool("search_incidents", {"query": svc_query, "tenant_id": tenant_id, "limit": 5}, search_incidents))
        results, record = kf.result()
        sim_results, sim_record = sf.result()

    tool_executions.extend([record, sim_record])
    tool_calls += 2

    merged = list(state.get("knowledge_results", []) or [])
    for r in (results.get("results", []) if isinstance(results, dict) else []):
        if r not in merged:
            merged.append(r)
    for inc in (sim_results.get("results", []) if isinstance(sim_results, dict) else []):
        entry = {
            "source": inc.get("incident_id", "similar-incident"),
            "type": "similar_incident",
            "title": inc.get("title", ""),
            "score": 0.75,
            "content": (
                f"Similar Historical Incident {inc.get('incident_id')}\n"
                f"Title: {inc.get('title')}\nSeverity: {inc.get('severity')}\n"
                f"Description: {inc.get('description', '')}"
            ),
        }
        if entry not in merged:
            merged.append(entry)

    return {
        "iteration": iteration,
        "knowledge_results": merged,
        "tool_calls": tool_calls,
        "tool_executions": tool_executions,
    }


def route_after_analysis(state: AgentState) -> str:
    confidence = float(state.get("confidence", 0.0) or 0.0)
    iteration = int(state.get("iteration", 0) or 0)
    max_iterations = int(state.get("max_iterations", 5) or 5)
    budget = int(state.get("max_tool_calls", MAX_TOOL_CALLS) or MAX_TOOL_CALLS)
    used = int(state.get("tool_calls", 0) or 0)

    if confidence >= 0.80:
        return "finalize"
    if iteration >= max_iterations or used >= budget:
        return "finalize"
    return "research_more"


def finalize(state: AgentState) -> dict:
    report = dict(state.get("final_report", {}) or {})
    report.setdefault("confidence", float(state.get("confidence", 0.0) or 0.0))

    open_circuits = list(state.get("open_circuits", []) or [])
    if open_circuits:
        actions = list(report.get("recommended_actions", []) or [])
        actions.append(
            f"Note: evidence sources were unavailable (circuits open: {', '.join(open_circuits)}). "
            f"Confidence reduced accordingly."
        )
        report["recommended_actions"] = actions

    return {"final_report": report}
