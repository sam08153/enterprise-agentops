"""
Tool policy / safety boundary at the agent layer.

This policy sits inside the LangGraph agent BEFORE any tool is invoked.
All agent tool calls pass through authorize_tool() before execution.

For PostgreSQL-backed data (incidents, documents, runbooks, history),
the actual enforcement now happens inside the PostgreSQL MCP server:
  - Authentication
  - Authorization (permission levels: READ / WRITE / HIGH_RISK / CRITICAL)
  - Tenant isolation (trusted security context, never model-supplied)
  - Input validation (bounded lengths, types, ranges)
  - Rate limiting (per-tool, per-tenant)
  - Result caps (max 20 records)
  - Audit logging

This file provides a lightweight second layer at the agent side.
"""

READ_ONLY_TOOLS: set[str] = {
    "get_incident",
    "search_incidents",
    "get_incident_history",
    "search_documents",
    "get_document",
    "search_knowledge",
    "get_logs",
    "get_metrics",
    "get_recent_deployment",
}


def authorize_tool(tool_name: str) -> bool:
    """
    Authorize a tool call at the agent layer.

    Returns True if the tool is on the READ_ONLY allowlist.
    Returns False if the tool is not listed (blocked pending explicit approval).

    Note that for PostgreSQL MCP tools, a second and stricter policy check
    happens inside the MCP server, including tenant isolation and rate limits.

    Architecture:
      Agent Node → authorize_tool() → MCP Client → MCP Policy Engine → DB
    """
    return tool_name in READ_ONLY_TOOLS


MCP_TOOL_PERMISSIONS: dict[str, str] = {
    "get_incident": "READ",
    "search_incidents": "READ",
    "get_incident_history": "READ",
    "search_documents": "READ",
    "get_document": "READ",
    "search_knowledge": "READ",
}
