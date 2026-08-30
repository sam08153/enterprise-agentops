from __future__ import annotations

from typing import Optional

from app.mcp_client import call_mcp_tool


def get_incident(incident_id: str, tenant_id: str = "demo") -> dict:
    """
    Retrieve a single incident by its identifier via the PostgreSQL MCP server.

    Applies tenant isolation, authorization, input validation, rate limits,
    and audit logging through the MCP policy engine.
    """
    result = call_mcp_tool(
        tool_name="get_incident",
        arguments={"incident_id": incident_id},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    inc = result.get("incident") if isinstance(result, dict) else None
    if inc:
        return dict(inc)
    if "error" in result:
        return {"incident_id": incident_id, "error": result["error"]}
    return {
        "incident_id": incident_id,
        "service": "unknown",
        "severity": "UNKNOWN",
        "error_rate": "0%",
        "started_at": "",
        "description": result.get("message", "Incident not found"),
    }


def search_incidents(query: str, tenant_id: str = "demo", limit: int = 10) -> dict:
    """
    Search incidents via the PostgreSQL MCP server.
    """
    result = call_mcp_tool(
        tool_name="search_incidents",
        arguments={"query": query, "limit": limit},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    results = result.get("results", []) if isinstance(result, dict) else []
    return {
        "query": query,
        "tenant_id": tenant_id,
        "results": results,
        "total_returned": len(results),
    }


def get_incident_history(service: str, tenant_id: str = "demo", limit: int = 10) -> dict:
    """
    Retrieve the full incident history for a service via the PostgreSQL MCP server.
    """
    result = call_mcp_tool(
        tool_name="get_incident_history",
        arguments={"service": service, "limit": limit},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    results = result.get("results", []) if isinstance(result, dict) else []
    return {
        "service": service,
        "tenant_id": tenant_id,
        "results": results,
        "total_returned": len(results),
    }


GET_INCIDENT_TOOL_DEFINITION = {
    "name": "get_incident",
    "description": (
        "Retrieve a single incident by its identifier via the PostgreSQL MCP server. "
        "Returns severity, error rate, affected service, description, and timeline. "
        "Enforces tenant isolation, policy, rate limits, and audit logging."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {
                "type": "string",
                "description": "The unique incident identifier, e.g. INC-0912",
            }
        },
        "required": ["incident_id"],
    },
}

SEARCH_INCIDENTS_TOOL_DEFINITION = {
    "name": "search_incidents",
    "description": (
        "Search across all incidents using a free-text query against title, description, "
        "service, and severity. Results are bounded (max 20) and ordered by recency/relevance. "
        "Use this for finding similar historical incidents during root cause analysis."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query, e.g. 'payment timeout regression'",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (1-20)",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

GET_INCIDENT_HISTORY_TOOL_DEFINITION = {
    "name": "get_incident_history",
    "description": (
        "Retrieve the full incident history for a specific service. "
        "Returns all incidents affecting that service, ordered by recency. "
        "Use this to identify recurring failure patterns for a given service."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "Service name, e.g. payment-service",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (1-20)",
                "default": 10,
            },
        },
        "required": ["service"],
    },
}
