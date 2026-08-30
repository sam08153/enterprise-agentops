from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("MOCK_MODE", "true")


def test_mcp_client():
    print("=" * 70)
    print("DAY 5: PostgreSQL MCP + LangGraph Integration Test Suite")
    print("=" * 70)
    print()

    from app.mcp_client import mcp_client

    client = mcp_client()

    print("--- Part 1: MCP Client Adapter (direct tool calls)")
    print()

    all_ok = True
    tests = [
        ("get_incident", {"incident_id": "INC-0912"}, "tenant=demo"),
        ("search_incidents", {"query": "payment timeout", "limit": 5}, "tenant=demo"),
        ("get_incident_history", {"service": "payment-service", "limit": 5}, "tenant=demo"),
        ("search_documents", {"query": "payment", "limit": 5}, "tenant=demo"),
        ("get_document", {"document_id": "DOC-001"}, "tenant=demo"),
        ("get_document", {"document_id": "runbooks/payment-service"}, "tenant=demo"),
    ]

    for tool_name, args, ctx in tests:
        try:
            result = client.call_tool(
                tool_name, args, tenant_id="demo", agent_name="rca-agent"
            )
        except Exception as e:
            print(f"  FAIL {tool_name}: {type(e).__name__}: {e}")
            all_ok = False
            continue

        status = result.get("_status", "?")
        duration = result.get("_duration_ms", "?")

        if result.get("_status") in ("SUCCESS",):
            total = result.get("total_returned")
            total_str = f" total={total}" if total is not None else ""
            inc = result.get("incident")
            doc = result.get("document")
            extra = ""
            if isinstance(inc, dict):
                extra = f" incident_id={inc.get('incident_id')} svc={inc.get('service')}"
            elif isinstance(doc, dict):
                extra = f" doc_id={doc.get('document_id')} title={doc.get('title')}"
            print(f"  OK   {tool_name:<20s}  status={status} ms={duration}{total_str}{extra}")
        elif "error" in result:
            print(f"  FAIL {tool_name:<20s}  status={status}  error={result.get('error')}")
            all_ok = False
        elif result.get("message"):
            print(f"  WARN {tool_name:<20s}  status={status} ms={duration}  message={result.get('message')}")
        else:
            keys = sorted(result.keys())
            print(f"  OK   {tool_name:<20s}  status={status} ms={duration} keys={keys}")

    print()

    if not all_ok:
        print("Part 1 FAILED")
        return False
    print("Part 1 PASSED — all MCP client tool calls work correctly.")
    print()

    print("--- Part 2: LangGraph Agent + MCP (end-to-end, mock LLM)")
    print()

    from app.agent.graph import run_investigation_graph

    print("Running investigation for INC-0912 (tenant=demo, mock_mode=True)")
    print()

    response = run_investigation_graph(
        incident_id="INC-0912",
        tenant_id="demo",
        thread_id="test-thread-mcp-day5",
        max_iterations=1,
    )

    print(f"  incident_id       : {response.incident_id}")
    print(f"  service           : {response.service}")
    print(f"  summary len       : {len(response.summary)} chars")
    print(f"  root_cause len    : {len(response.root_cause)} chars")
    print(f"  confidence        : {response.confidence}")
    print(f"  evidence count    : {len(response.evidence)} items")
    print(f"  actions count     : {len(response.recommended_actions)} items")
    print(f"  tool_calls        : {response.tool_calls}")
    print(f"  input_tokens      : {response.input_tokens}")
    print(f"  output_tokens     : {response.output_tokens}")
    print(f"  tool_executions   : {len(response.tool_executions)} records")
    print()

    expected_minimum_tool_calls = 5
    if response.tool_calls >= expected_minimum_tool_calls:
        print(f"  OK   tool calls ({response.tool_calls} >= {expected_minimum_tool_calls}) expected")
    else:
        print(f"  WARN tool calls low: only {response.tool_calls} < {expected_minimum_tool_calls}")

    if response.service == "payment-service":
        print(f"  OK   service is payment-service (matches MCP incident)")
    else:
        print(f"  WARN service={response.service} (expected payment-service)")
        all_ok = False

    if 0.0 <= response.confidence <= 1.0:
        print(f"  OK   valid confidence")
    else:
        print(f"  FAIL confidence out of range: {response.confidence}")
        all_ok = False

    print()

    print("--- Part 3: Audit — tool execution records (audit trail)")
    print()
    mcp_tools_seen = set()
    for i, rec in enumerate(response.tool_executions):
        try:
            tn = rec.tool_name
            st = rec.status
            dm = rec.duration_ms
        except Exception:
            tn = rec.get("tool_name", "?") if isinstance(rec, dict) else "?"
            st = rec.get("status", "?") if isinstance(rec, dict) else "?"
            dm = rec.get("duration_ms", "?") if isinstance(rec, dict) else "?"
        print(f"  #{i+1:<2} {tn:<20s} status={st:<14s} duration_ms={dm}")
        mcp_tools_seen.add(tn)

    print()
    required_mcp_tools = {"get_incident", "get_incident_history", "search_incidents"}
    missing = required_mcp_tools - mcp_tools_seen
    if not missing:
        print(f"  OK   required MCP tools used: {required_mcp_tools}")
    else:
        print(f"  WARN missing MCP tools from audit trail: {missing}")
    print()
    return all_ok


if __name__ == "__main__":
    success = test_mcp_client()
    print("=" * 70)
    if success:
        print("ALL DAY 5 INTEGRATION TESTS PASSED")
        sys.exit(0)
    print("SOME TESTS FAILED")
    sys.exit(1)
