from app.mcp_client import call_mcp_tool


def search_knowledge(query: str, tenant_id: str = "demo") -> dict:
    """
    Search organizational knowledge (runbooks, incidents, architecture docs)
    via the PostgreSQL MCP server.

    All queries are tenant-isolated, rate-limited, input-validated, and audited
    through the MCP policy engine.
    """
    result = call_mcp_tool(
        tool_name="search_documents",
        arguments={"query": query, "limit": 10},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    doc_results = result.get("results", []) if isinstance(result, dict) else []

    incident_result = call_mcp_tool(
        tool_name="search_incidents",
        arguments={"query": query, "limit": 5},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    inc_results = incident_result.get("results", []) if isinstance(incident_result, dict) else []

    combined = []
    for r in doc_results:
        combined.append(
            {
                "source": r.get("source") or r.get("title") or "document",
                "content": r.get("content", ""),
                "score": 0.9,
                "type": "document",
                "title": r.get("title", ""),
            }
        )
    for inc in inc_results:
        combined.append(
            {
                "source": inc.get("incident_id", "incident"),
                "content": (
                    f"Incident {inc.get('incident_id')}: {inc.get('title', '')}\n"
                    f"Severity: {inc.get('severity')}  Status: {inc.get('status')}\n"
                    f"{inc.get('description', '')}"
                ),
                "score": 0.7,
                "type": "incident",
                "title": inc.get("title", ""),
            }
        )
    return {
        "query": query,
        "tenant_id": tenant_id,
        "results": combined,
    }


def get_document(document_id: str, tenant_id: str = "demo") -> dict:
    """
    Retrieve a single document by ID or source path via the PostgreSQL MCP server.
    """
    result = call_mcp_tool(
        tool_name="get_document",
        arguments={"document_id": document_id},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    doc = result.get("document") if isinstance(result, dict) else None
    if doc:
        return {"document": doc}
    return {"document": None, "message": result.get("message", "Not found")}


SEARCH_KNOWLEDGE_TOOL_DEFINITION = {
    "name": "search_knowledge",
    "description": (
        "Search organizational knowledge (runbooks, incidents, architecture docs, postmortems) "
        "via the PostgreSQL MCP server. Uses keyword search across document titles, content, "
        "sources AND historical incident records. "
        "All queries enforce tenant isolation, policy validation, rate limits, and audit logging."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "tenant_id": {"type": "string", "description": "Tenant name/id. Defaults to 'demo'."},
        },
        "required": ["query"],
    },
}

GET_DOCUMENT_TOOL_DEFINITION = {
    "name": "get_document",
    "description": (
        "Retrieve a single knowledge document by its ID or source path "
        "(e.g. runbooks/payment-service or DOC-001) via the PostgreSQL MCP server. "
        "Returns the full document body including remediation steps, architecture details, "
        "or postmortem analysis."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "document_id": {
                "type": "string",
                "description": "Document ID or source path, e.g. DOC-001 or runbooks/payment-service",
            }
        },
        "required": ["document_id"],
    },
}
