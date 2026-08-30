from __future__ import annotations

from app.aws_mcp_client import aws_mcp_client


def get_metrics(service: str, window_minutes: int = 30, tenant_id: str = "demo") -> dict:
    result = aws_mcp_client().call_tool(
        "get_service_metrics",
        {"service": service, "window_minutes": window_minutes},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    return result


METRICS_TOOL_DEFINITION = {
    "name": "get_metrics",
    "description": "Retrieve structured operational metrics for a service: error rate %, p95/p50 latency, request count, CPU %, memory %, DB pool utilization, with deltas vs previous window.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name, e.g. payment-service"},
            "window_minutes": {"type": "integer", "description": "Aggregation window (1-360 minutes, default 30)"},
        },
        "required": ["service"],
    },
}
