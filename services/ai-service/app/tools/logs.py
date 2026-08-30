from __future__ import annotations

from app.aws_mcp_client import aws_mcp_client


def get_logs(service: str, minutes: int = 30, limit: int = 200, tenant_id: str = "demo") -> dict:
    result = aws_mcp_client().call_tool(
        "get_cloudwatch_logs",
        {"service": service, "minutes": minutes, "limit": limit},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    return result


def get_service_health(service: str, tenant_id: str = "demo") -> dict:
    result = aws_mcp_client().call_tool(
        "get_service_health",
        {"service": service},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    return result


LOGS_TOOL_DEFINITION = {
    "name": "get_logs",
    "description": "Retrieve application logs from AWS CloudWatch for a specific service. Chronologically ordered with level-count summary. Bounded lookback window (1-120 minutes) and safe row limit.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name, e.g. payment-service"},
            "minutes": {"type": "integer", "description": "Lookback window in minutes (1-120, default 30)"},
            "limit": {"type": "integer", "description": "Max log entries (capped at 200)"},
        },
        "required": ["service"],
    },
}

GET_SERVICE_HEALTH_TOOL_DEFINITION = {
    "name": "get_service_health",
    "description": "High-level service health snapshot: overall status, healthy/unhealthy instance counts, capacity, health percent.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name, e.g. payment-service"},
        },
        "required": ["service"],
    },
}
