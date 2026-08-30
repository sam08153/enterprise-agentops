from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("postgres-mcp")

from database import Database, get_db
from tools import (
    execute_tool,
    get_all_tool_definitions,
    TOOL_DEFINITIONS,
)

_MCP_AVAILABLE = True
try:
    from mcp.server.fastmcp import FastMCP, Context
except Exception as e:  # pragma: no cover - import guard
    _MCP_AVAILABLE = False
    logger.warning("MCP SDK not available: %s. Running in standalone mode only.", e)

    class Context:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self._meta: Dict[str, Any] = {}

        @property
        def meta(self) -> Dict[str, Any]:
            return self._meta


SERVER_NAME = "postgres-mcp"
SERVER_VERSION = "0.1.0"

DEFAULT_TENANT_ID = "demo"
DEFAULT_AGENT_NAME = "rca-agent"


def _extract_context(ctx: Any) -> tuple[str, str]:
    meta: Dict[str, Any] = {}
    try:
        meta = dict(getattr(ctx, "meta", {}) or {})
    except Exception:
        meta = {}

    tenant_id = str(
        meta.get("tenant_id")
        or meta.get("tenant")
        or os.environ.get("MCP_DEFAULT_TENANT_ID")
        or DEFAULT_TENANT_ID
    ).strip()
    agent_name = str(
        meta.get("agent_name")
        or meta.get("agent")
        or os.environ.get("MCP_DEFAULT_AGENT_NAME")
        or DEFAULT_AGENT_NAME
    ).strip()
    return tenant_id, agent_name


def _build_server():
    if not _MCP_AVAILABLE:
        return None

    mcp = FastMCP(
        SERVER_NAME,
        version=SERVER_VERSION,
        dependencies=[],
        description=(
            "PostgreSQL MCP server providing read-only access to enterprise incident, "
            "document, and runbook data with tenant isolation, policy enforcement, "
            "rate limiting, and audit logging."
        ),
    )

    @mcp.tool(name="get_incident")
    def get_incident(
        incident_id: str,
        ctx: Context,
    ) -> str:
        """
        Retrieve a single incident by its identifier (e.g. INC-0912).

        Returns full incident metadata including severity, status, description,
        affected service, error rate, and timestamp when the incident began.
        Use this when you already know the incident ID and need complete details
        about that specific incident for root cause analysis.

        Args:
            incident_id: The unique incident identifier, e.g. INC-0912
        """
        tenant_id, agent_name = _extract_context(ctx)
        result = execute_tool(
            tool_name="get_incident",
            arguments={"incident_id": incident_id},
            agent_name=agent_name,
            tenant_id=tenant_id,
        )
        return json.dumps(result.output, indent=2, sort_keys=True)

    @mcp.tool(name="search_incidents")
    def search_incidents(
        query: str,
        limit: int = 20,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        Search across all historical and active incidents using a free-text query.

        The query is matched against incident titles, descriptions, affected services,
        severity levels, and incident IDs. Results are ordered by recency and relevance
        with a maximum of 20 results returned.

        Use this when investigating failure patterns, looking for similar past incidents,
        or discovering incidents related to a specific service (e.g. 'payment timeout')
        or error type (e.g. 'HTTP 500 database pool').

        Args:
            query: Free-text search query. Matches against title, description, service, and severity.
            limit: Maximum number of results to return (1-20). Defaults to 20.
        """
        tenant_id, agent_name = _extract_context(ctx)
        result = execute_tool(
            tool_name="search_incidents",
            arguments={"query": query, "limit": limit},
            agent_name=agent_name,
            tenant_id=tenant_id,
        )
        return json.dumps(result.output, indent=2, sort_keys=True)

    @mcp.tool(name="get_incident_history")
    def get_incident_history(
        service: str,
        limit: int = 20,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        Retrieve the complete incident history for a specific service.

        Returns all incidents that have affected the given service, ordered by
        most recent first with a maximum of 20 results.

        Use this when performing root cause analysis and you need to understand
        recurring failure patterns, seasonal issues, or service-specific incident
        trends over time. For example, pass 'payment-service' to see every historical
        incident that impacted the payment service.

        Args:
            service: The service name to retrieve incident history for, e.g. 'payment-service'
            limit: Maximum number of results to return (1-20). Defaults to 20.
        """
        tenant_id, agent_name = _extract_context(ctx)
        result = execute_tool(
            tool_name="get_incident_history",
            arguments={"service": service, "limit": limit},
            agent_name=agent_name,
            tenant_id=tenant_id,
        )
        return json.dumps(result.output, indent=2, sort_keys=True)

    @mcp.tool(name="search_documents")
    def search_documents(
        query: str,
        limit: int = 20,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        Search organizational knowledge documents using a free-text query.

        Document corpus includes runbooks, architecture guides, postmortems,
        standard operating procedures, and design documents.
        The query matches against document titles, full content body, and source paths.
        Returns up to 20 matching documents with title, source, content preview, and metadata.

        Use this when looking for documented procedures, architectural context, known issues,
        or remediation playbooks during incident investigation.

        Args:
            query: Free-text search query. Matches against document title, content, and source.
            limit: Maximum number of results to return (1-20). Defaults to 20.
        """
        tenant_id, agent_name = _extract_context(ctx)
        result = execute_tool(
            tool_name="search_documents",
            arguments={"query": query, "limit": limit},
            agent_name=agent_name,
            tenant_id=tenant_id,
        )
        return json.dumps(result.output, indent=2, sort_keys=True)

    @mcp.tool(name="get_document")
    def get_document(
        document_id: str,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        Retrieve a single full document by its identifier (e.g. DOC-001) or
        source path (e.g. 'runbooks/payment-service').

        Returns the complete document content including title, full body text,
        source location, and creation metadata.

        Use this after you have found a relevant document summary from search_documents
        and need to read the full content for detailed operational guidance,
        step-by-step remediation instructions, or deep architectural context.

        Args:
            document_id: Document identifier or source path, e.g. DOC-001 or runbooks/payment-service
        """
        tenant_id, agent_name = _extract_context(ctx)
        result = execute_tool(
            tool_name="get_document",
            arguments={"document_id": document_id},
            agent_name=agent_name,
            tenant_id=tenant_id,
        )
        return json.dumps(result.output, indent=2, sort_keys=True)

    @mcp.resource("runbooks://{service}")
    def runbook_resource(service: str) -> str:
        """
        Retrieve the operational runbook for a given service.

        Runbooks include documented symptoms, initial investigation steps,
        deployment-related troubleshooting, and rollback procedures.
        Resources are read-only static data — use this to quickly load
        service-specific operational guidance during an investigation.

        Example URI: runbooks://payment-service
        """
        db = get_db()
        tenant_id = os.environ.get("MCP_DEFAULT_TENANT_ID", DEFAULT_TENANT_ID)
        doc = db.get_runbook_resource(service, tenant_id)
        if doc is None:
            return (
                f"# Runbook Not Found\n\n"
                f"No runbook available for service '{service}'.\n"
                f"Try searching documents with: search_documents('runbook {service}')"
            )
        content = doc.get("content", "")
        if not content.startswith("#"):
            title = doc.get("title", service)
            content = f"# {title}\n\n{content}"
        return content

    @mcp.resource("incidents://{incident_id}")
    def incident_resource(incident_id: str) -> str:
        """
        Retrieve incident details as a read-only resource.

        Use this resource URI to quickly load a known incident's details
        into context without calling the get_incident tool.

        Example URI: incidents://INC-0912
        """
        db = get_db()
        tenant_id = os.environ.get("MCP_DEFAULT_TENANT_ID", DEFAULT_TENANT_ID)
        inc = db.get_incident(incident_id, tenant_id)
        if inc is None:
            return (
                f"# Incident Not Found\n\nNo incident record exists with ID '{incident_id}'."
            )
        return (
            f"# Incident {inc.get('incident_id', incident_id)}\n\n"
            f"- **Title:** {inc.get('title', 'N/A')}\n"
            f"- **Service:** {inc.get('service', 'N/A')}\n"
            f"- **Severity:** {inc.get('severity', 'N/A')}\n"
            f"- **Status:** {inc.get('status', 'N/A')}\n"
            f"- **Error Rate:** {inc.get('error_rate', 'N/A')}\n"
            f"- **Started At:** {inc.get('started_at', 'N/A')}\n\n"
            f"## Description\n\n{inc.get('description', 'N/A')}\n"
        )

    @mcp.prompt(name="incident-investigation")
    def incident_investigation_prompt(service: str = "the affected service") -> str:
        """
        Standardized incident investigation prompt template.

        Provides a structured, reusable framework for root cause analysis
        that guides the investigator through all relevant evidence sources.
        The template emphasizes collecting evidence before forming conclusions
        and requires explicit confidence scoring with supporting citations.

        Use this prompt at the beginning of any formal incident investigation
        to ensure consistent coverage of logs, metrics, deployments, history,
        and runbook references.

        Args:
            service: The affected service name to tailor the investigation scope.
        """
        return f"""You are the Lead Site Reliability Engineer performing a formal Root Cause Analysis for {service}.

## Investigation Protocol

Follow these steps in order. Do NOT skip evidence collection.

### 1. Load Contextual Resources
- Load resource: `runbooks://{service}`
- Search recent incidents using: search_incidents(query="{service} timeout error regression")
- Get full incident history for this service using: get_incident_history(service="{service}")

### 2. Gather Supporting Evidence
Collect evidence from these sources (use the appropriate tools for each):
- **Recent application logs** (last 30-60 minutes) — look for stack traces, exceptions, timeout patterns
- **Deployment history** — identify any recent releases, config changes, or feature flags toggled near the incident start
- **Service metrics** — error rate, latency percentiles (p50/p95/p99), throughput, saturation
- **Similar historical incidents** — compare symptoms and causes from INC-* records returned by search

### 3. Cross-Reference Runbooks
- Read the full runbook for {service} using: get_document(document_id="runbooks/{service}")
- Verify each runbook symptom against gathered evidence
- Follow runbook triage steps BEFORE proposing a root cause

### 4. Required Output Format
Return ONLY a valid JSON object with:
{{
  "summary": "2-3 sentence executive summary of the incident",
  "root_cause": "Single most likely root cause with specific evidence",
  "confidence": 0.0 to 1.0,
  "evidence": [
    "Specific log line or metric showing X",
    "Deployment Y at Z time introduced regression",
    "Historical incident INC-1234 had identical failure mode"
  ],
  "recommended_actions": [
    "Immediate remediation step 1",
    "Short-term mitigation step 2",
    "Long-term preventative action"
  ],
  "alternative_causes": [
    "Plausible cause A with reason for lower confidence",
    "Plausible cause B with reason for lower confidence"
  ]
}}

### 5. Confidence Scoring Rules
- >0.90: Multiple strong, direct evidence sources all agreeing
- 0.70-0.90: Good evidence, one or two minor unknowns remain
- 0.40-0.70: Circumstantial evidence, requires more data collection
- <0.40: Speculation — indicate you need more evidence explicitly

If confidence is below 0.70, explicitly call out which evidence is missing and which additional tool calls would raise confidence.
"""

    @mcp.prompt(name="document-dive")
    def document_dive_prompt(query: str = "the investigation topic") -> str:
        """
        Deep knowledge retrieval prompt for investigating complex or ambiguous topics.

        Use this when you need to systematically explore the knowledge base,
        compare multiple documents, and synthesize cross-references between
        runbooks, architecture, and postmortems.

        Args:
            query: The topic or question you need to research deeply.
        """
        return f"""Research Task: Deep knowledge base exploration on the topic: "{query}"

## Research Protocol

1. **Broad Search**: Use search_documents(query="{query}") with several query variants to cast a wide net.
   Suggested variants:
   - search_documents(query="runbook {query}")
   - search_documents(query="architecture {query}")
   - search_documents(query="postmortem {query}")

2. **Deep Reading**: For the top 3 most relevant documents:
   - Use get_document(document_id=...) to read the FULL content
   - Do NOT rely on search snippets alone

3. **Synthesize Cross-References**:
   - Identify contradictions or tensions between documents
   - Highlight where postmortems validate or invalidate runbook assumptions
   - Note architectural constraints that may impact incident resolution

4. **Output**: Produce a structured research brief summarizing findings with explicit document citations (source + title).
"""

    return mcp


def run_standalone_test() -> int:
    """Directly exercise the tool execution layer without MCP transport."""

    print("=" * 70)
    print(f"PostgreSQL MCP Server v{SERVER_VERSION} — STANDALONE TEST MODE")
    print("=" * 70)
    print()

    db = get_db()
    tenant_id = "demo"
    agent_name = "rca-agent"

    test_cases = [
        (
            "1. search_incidents('payment timeout')",
            "search_incidents",
            {"query": "payment timeout", "limit": 5},
        ),
        (
            "2. get_incident('INC-0912')",
            "get_incident",
            {"incident_id": "INC-0912"},
        ),
        (
            "3. get_incident_history('payment-service')",
            "get_incident_history",
            {"service": "payment-service", "limit": 5},
        ),
        (
            "4. search_documents('runbook payment timeout')",
            "search_documents",
            {"query": "runbook payment timeout", "limit": 5},
        ),
        (
            "5. get_document('DOC-001')",
            "get_document",
            {"document_id": "DOC-001"},
        ),
        (
            "6. get_document('runbooks/payment-service')",
            "get_document",
            {"document_id": "runbooks/payment-service"},
        ),
        (
            "7. Resource test: runbooks://payment-service",
            "__RESOURCE__",
            {"kind": "runbook", "service": "payment-service"},
        ),
        (
            "8. Input validation: empty query",
            "search_incidents",
            {"query": ""},
        ),
        (
            "9. Input validation: query too long (1000 chars)",
            "search_incidents",
            {"query": "x" * 1000},
        ),
        (
            "10. Not found: get_incident('INC-9999')",
            "get_incident",
            {"incident_id": "INC-9999"},
        ),
    ]

    all_ok = True

    for label, tool_name, args in test_cases:
        print(f"--- {label}")
        print(f"      args: {json.dumps(args, default=str)}")

        if tool_name == "__RESOURCE__":
            kind = args.get("kind")
            if kind == "runbook":
                doc = db.get_runbook_resource(args.get("service", ""), tenant_id)
                if doc:
                    preview = (doc.get("content", "") or "")[:200]
                    print(f"   OK       — {doc.get('title')} | {len(doc.get('content', ''))} chars | preview: {preview!r}...")
                else:
                    print(f"   NOT FOUND")
                    all_ok = False
        else:
            result = execute_tool(
                tool_name=tool_name,
                arguments=args,
                agent_name=agent_name,
                tenant_id=tenant_id,
                db=db,
            )
            if result.success:
                output = result.output
                total = output.get("total_returned")
                if total is not None:
                    print(
                        f"   OK       — status={result.status} duration_ms={result.duration_ms} "
                        f"total_returned={total}"
                    )
                else:
                    keys = sorted(output.keys())
                    print(
                        f"   OK       — status={result.status} duration_ms={result.duration_ms} "
                        f"keys={keys}"
                    )
                    for k in ["message", "error"]:
                        if k in output:
                            print(f"             {k}: {str(output[k])[:160]}")
            else:
                print(
                    f"   EXPECTED POLICY/ERROR — status={result.status} duration_ms={result.duration_ms} "
                    f"error={result.error!r}"
                )
                if result.status == "FAILED":
                    all_ok = False
        print()

    print("=" * 70)
    if all_ok:
        print("ALL STANDALONE TESTS PASSED")
        return 0
    print("SOME TESTS FAILED — see output above")
    return 1


def print_capabilities() -> None:
    print("=" * 70)
    print(f"PostgreSQL MCP Server v{SERVER_VERSION} Capabilities")
    print("=" * 70)
    print()
    print("TOOLS:")
    for td in TOOL_DEFINITIONS:
        name = td.name
        policy = {
            "get_incident": "60 req/min",
            "search_incidents": "20 req/min",
            "get_incident_history": "30 req/min",
            "search_documents": "20 req/min",
            "get_document": "60 req/min",
        }.get(name, "?")
        print(f"  - {name:<30s}  rate_limit={policy}")
    print()
    print("RESOURCES:")
    print("  - runbooks://{service}             Service runbook (read-only)")
    print("  - incidents://{incident_id}        Incident details (read-only)")
    print()
    print("PROMPTS:")
    print("  - incident-investigation           Standardized RCA template")
    print("  - document-dive                    Deep knowledge research template")
    print()
    print("POLICY:")
    print("  - All tools enforce READ-only permission")
    print("  - Tenant isolation via trusted security context")
    print("  - Input validation on all parameters")
    print("  - Result limits capped at 20 records")
    print("  - Audit logging for every tool call")
    print("  - Rate limiting per (tool, tenant) pair")
    print("=" * 70)


def main(argv: Optional[list[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--capabilities" in argv or "-c" in argv:
        print_capabilities()
        return 0

    if "--test" in argv or "--standalone" in argv or "-t" in argv:
        return run_standalone_test()

    if not _MCP_AVAILABLE:
        print(
            "ERROR: MCP SDK is not installed. Install with: pip install mcp[cli]",
            file=sys.stderr,
        )
        print(
            "       For standalone testing run again with: --test",
            file=sys.stderr,
        )
        return 2

    server = _build_server()
    try:
        server.run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
