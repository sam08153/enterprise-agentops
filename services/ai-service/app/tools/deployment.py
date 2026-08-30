from __future__ import annotations

from app.aws_mcp_client import aws_mcp_client


def get_recent_deployment(service: str, tenant_id: str = "demo") -> dict:
    result = aws_mcp_client().call_tool(
        "get_recent_deployment",
        {"service": service},
        tenant_id=tenant_id,
        agent_name="rca-agent",
    )
    return result


DEPLOYMENT_TOOL_DEFINITION = {
    "name": "get_recent_deployment",
    "description": "Retrieve metadata about the most recent production deployment for a service: version, deployed_at timestamp, previous version, commit SHA, deploying actor, and status.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {"type": "string", "description": "Service name, e.g. payment-service"},
        },
        "required": ["service"],
    },
}
