from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from database import Database, get_db
from policy import (
    authorize_and_validate,
    policy_engine,
    PolicyError,
    ToolPolicy,
    TOOL_POLICIES,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionResult:
    success: bool
    output: Dict[str, Any]
    duration_ms: int
    error: Optional[str] = None
    status: str = "SUCCESS"


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]


TOOL_DEFINITIONS: List[ToolDefinition] = [
    ToolDefinition(
        name="get_incident",
        description=(
            "Retrieve a single incident by its identifier (e.g. INC-0912). "
            "Returns full incident metadata including severity, status, description, "
            "affected service, error rate, and timestamp when the incident began. "
            "Use this when you already know the incident ID and need complete details "
            "about that specific incident for root cause analysis."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "The unique incident identifier, e.g. INC-0912",
                },
            },
            "required": ["incident_id"],
        },
    ),
    ToolDefinition(
        name="search_incidents",
        description=(
            "Search across all historical and active incidents using a free-text query. "
            "The query is matched against incident titles, descriptions, affected services, "
            "severity levels, and incident IDs. Results are ordered by recency and relevance "
            "with a maximum of 20 results returned. "
            "Use this when investigating failure patterns, looking for similar past incidents, "
            "or discovering incidents related to a specific service (e.g. 'payment timeout') "
            "or error type (e.g. 'HTTP 500 database pool')."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search query. Matches against title, description, service, and severity.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-20). Defaults to 20.",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="get_incident_history",
        description=(
            "Retrieve the complete incident history for a specific service. "
            "Returns all incidents that have affected the given service, ordered by "
            "most recent first with a maximum of 20 results. "
            "Use this when performing root cause analysis and you need to understand "
            "recurring failure patterns, seasonal issues, or service-specific incident "
            "trends over time. For example, pass 'payment-service' to see every historical "
            "incident that impacted the payment service."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "The service name to retrieve incident history for, e.g. 'payment-service'",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-20). Defaults to 20.",
                    "default": 20,
                },
            },
            "required": ["service"],
        },
    ),
    ToolDefinition(
        name="search_documents",
        description=(
            "Search organizational knowledge documents using a free-text query. "
            "Document corpus includes runbooks, architecture guides, postmortems, "
            "standard operating procedures, and design documents. "
            "The query matches against document titles, full content body, and source paths. "
            "Returns up to 20 matching documents with title, source, content preview, and metadata. "
            "Use this when looking for documented procedures, architectural context, known issues, "
            "or remediation playbooks during incident investigation."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search query. Matches against document title, content, and source.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-20). Defaults to 20.",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="get_document",
        description=(
            "Retrieve a single full document by its identifier (e.g. DOC-001) or "
            "source path (e.g. 'runbooks/payment-service'). "
            "Returns the complete document content including title, full body text, "
            "source location, and creation metadata. "
            "Use this after you have found a relevant document summary from search_documents "
            "and need to read the full content for detailed operational guidance, "
            "step-by-step remediation instructions, or deep architectural context."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "Document identifier or source path, e.g. DOC-001 or runbooks/payment-service",
                },
            },
            "required": ["document_id"],
        },
    ),
]


def _sanitize_result(result: Any) -> Any:
    if isinstance(result, dict):
        return {k: _sanitize_result(v) for k, v in result.items() if k not in ("tenant_id",)}
    if isinstance(result, list):
        return [_sanitize_result(v) for v in result]
    return result


def execute_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    agent_name: Optional[str] = None,
    tenant_id: Optional[str] = None,
    db: Optional[Database] = None,
) -> ToolExecutionResult:
    if db is None:
        db = get_db()

    started_at = time.monotonic()

    try:
        agent_clean, tenant_clean, policy, validated = authorize_and_validate(
            tool_name=tool_name,
            agent_name=agent_name,
            tenant_id=tenant_id,
            inputs=arguments,
        )
    except PolicyError as e:
        duration_ms = max(1, int((time.monotonic() - started_at) * 1000))
        logger.warning("Policy error on %s: %s", tool_name, e)
        try:
            db.audit_tool_execution(
                tool_name=tool_name,
                agent_name=agent_name or "unknown",
                tenant_id=tenant_id or "unknown",
                input_data=arguments,
                output_data={"error": str(e)},
                status="POLICY_DENIED",
                duration_ms=duration_ms,
            )
        except Exception:
            pass
        return ToolExecutionResult(
            success=False,
            output={"error": str(e), "error_type": type(e).__name__},
            duration_ms=duration_ms,
            error=str(e),
            status="POLICY_DENIED",
        )

    raw_output: Dict[str, Any] = {}
    try:
        if tool_name == "get_incident":
            raw_output = _get_incident_impl(db, tenant_clean, validated["incident_id"])
        elif tool_name == "search_incidents":
            limit = validated.get("limit", 20)
            raw_output = _search_incidents_impl(db, tenant_clean, validated["query"], limit)
        elif tool_name == "get_incident_history":
            limit = validated.get("limit", 20)
            raw_output = _get_incident_history_impl(db, tenant_clean, validated["service"], limit)
        elif tool_name == "search_documents":
            limit = validated.get("limit", 20)
            raw_output = _search_documents_impl(db, tenant_clean, validated["query"], limit)
        elif tool_name == "get_document":
            raw_output = _get_document_impl(db, tenant_clean, validated["document_id"])
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

        status = "SUCCESS"
        success = True
        error_msg = None

    except Exception as e:
        status = "FAILED"
        success = False
        error_msg = str(e)
        raw_output = {"error": str(e), "error_type": type(e).__name__}
        logger.exception("Tool execution failed: %s", tool_name)

    sanitized = _sanitize_result(raw_output)
    duration_ms = max(1, int((time.monotonic() - started_at) * 1000))

    try:
        db.audit_tool_execution(
            tool_name=tool_name,
            agent_name=agent_clean,
            tenant_id=tenant_clean,
            input_data=validated,
            output_data=sanitized if isinstance(sanitized, dict) else {"result": sanitized},
            status=status,
            duration_ms=duration_ms,
        )
    except Exception as audit_err:
        logger.warning("Audit logging failed: %s", audit_err)

    return ToolExecutionResult(
        success=success,
        output=sanitized if isinstance(sanitized, dict) else {"result": sanitized},
        duration_ms=duration_ms,
        error=error_msg,
        status=status,
    )


def _get_incident_impl(db: Database, tenant_id: str, incident_id: str) -> Dict[str, Any]:
    inc = db.get_incident(incident_id, tenant_id)
    if inc is None:
        return {"incident": None, "message": f"No incident found with id '{incident_id}'"}
    return {"incident": inc}


def _search_incidents_impl(db: Database, tenant_id: str, query: str, limit: int) -> Dict[str, Any]:
    results = db.search_incidents(query, tenant_id, limit=limit)
    return {
        "query": query,
        "total_returned": len(results),
        "results": results,
    }


def _get_incident_history_impl(db: Database, tenant_id: str, service: str, limit: int) -> Dict[str, Any]:
    results = db.get_incident_history(service, tenant_id, limit=limit)
    return {
        "service": service,
        "total_returned": len(results),
        "results": results,
    }


def _search_documents_impl(db: Database, tenant_id: str, query: str, limit: int) -> Dict[str, Any]:
    results = db.search_documents(query, tenant_id, limit=limit)
    return {
        "query": query,
        "total_returned": len(results),
        "results": results,
    }


def _get_document_impl(db: Database, tenant_id: str, document_id: str) -> Dict[str, Any]:
    doc = db.get_document(document_id, tenant_id)
    if doc is None:
        return {"document": None, "message": f"No document found with id '{document_id}'"}
    return {"document": doc}


def get_all_tool_definitions() -> List[ToolDefinition]:
    return list(TOOL_DEFINITIONS)


def get_tool_policy(tool_name: str) -> Optional[ToolPolicy]:
    return TOOL_POLICIES.get(tool_name)
