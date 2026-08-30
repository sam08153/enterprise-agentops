from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MCP_AWS_SERVER_DIR = Path(__file__).resolve().parents[3] / "mcp" / "aws-server"
MCP_USE_LOCAL = os.environ.get("MCP_USE_LOCAL", "true").lower() in ("1", "true", "yes")

_MCP_SDK_AVAILABLE = False
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_SDK_AVAILABLE = True
except Exception as e:
    logger.info("MCP SDK not available for AWS client: %s. Using local in-process mode.", e)

_cloudwatch_service_fn = None
_metrics_service_fn = None
_deployment_service_fn = None
_health_service_fn = None


def _load_fns():
    global _cloudwatch_service_fn, _metrics_service_fn, _deployment_service_fn, _health_service_fn
    if _cloudwatch_service_fn is not None:
        return
    if str(MCP_AWS_SERVER_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_AWS_SERVER_DIR))
    try:
        from services import aws_services as svc
        _cloudwatch_service_fn = svc.cloudwatch_service
        _metrics_service_fn = svc.metrics_service
        _deployment_service_fn = svc.deployment_service
        _health_service_fn = svc.health_service
    except Exception as e:
        logger.warning("Could not load AWS services: %s", e)


class AwsMCPClient:
    _instance: Optional["AwsMCPClient"] = None

    def __init__(self, default_agent: str = "rca-agent", default_tenant: str = "demo"):
        self._default_agent = default_agent
        self._default_tenant = default_tenant
        self._use_local = MCP_USE_LOCAL or not _MCP_SDK_AVAILABLE

    @classmethod
    def instance(cls) -> "AwsMCPClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ctx(self, tenant_id: Optional[str], agent_name: Optional[str]):
        tenant = (tenant_id or self._default_tenant or "demo").strip() or "demo"
        agent = (agent_name or self._default_agent or "rca-agent").strip() or "rca-agent"
        return tenant, agent

    def _call_local(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        _load_fns()
        if _cloudwatch_service_fn is None:
            return {"error": "AWS MCP services unavailable locally", "error_type": "ImportError"}
        try:
            if tool_name == "get_cloudwatch_logs":
                service = arguments["service"]
                minutes = int(arguments["minutes"])
                max_items = int(arguments.get("limit", 200))
                return _cloudwatch_service_fn().get_logs(service=service, minutes=minutes, max_items=max_items)
            if tool_name == "get_service_metrics":
                service = arguments["service"]
                window = int(arguments.get("window_minutes", 30))
                return _metrics_service_fn().get_metrics(service=service, window_minutes=window)
            if tool_name == "get_recent_deployment":
                service = arguments["service"]
                return _deployment_service_fn().get_recent(service=service)
            if tool_name == "get_service_health":
                service = arguments["service"]
                return _health_service_fn().get_health(service=service)
        except Exception as e:
            logger.exception("AWS MCP local call failed tool=%s", tool_name)
            return {"error": str(e), "error_type": type(e).__name__}
        return {"error": f"Unknown AWS tool: {tool_name}", "error_type": "UnknownTool"}

    def call_tool(self, tool_name, arguments, tenant_id=None, agent_name=None):
        tenant, agent = self._ctx(tenant_id, agent_name)
        if self._use_local:
            return self._call_local(tool_name, arguments)
        return self._call_stdio(tool_name, arguments, tenant, agent)

    def _call_stdio(self, tool_name, arguments, tenant, agent):
        if not _MCP_SDK_AVAILABLE:
            return {"error": "MCP SDK not installed", "error_type": "MissingMcpSdk"}
        server_script = str(MCP_AWS_SERVER_DIR / "server.py")
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
            env={**os.environ, "MCP_DEFAULT_TENANT_ID": tenant, "MCP_DEFAULT_AGENT_NAME": agent},
        )
        result_text = ""
        try:
            with stdio_client(server_params) as (read, write):
                with ClientSession(read, write) as session:
                    session.initialize()
                    call_result = session.call_tool(tool_name, arguments)
                    parts = getattr(call_result, "content", []) or []
                    if parts:
                        result_text = str(getattr(parts[0], "text", "") or "")
                    else:
                        result_text = str(call_result)
        except Exception as e:
            logger.exception("AWS MCP stdio call failed for tool %s", tool_name)
            return {"error": f"MCP stdio failed: {e}", "error_type": type(e).__name__, "_status": "FAILED"}
        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, dict):
                parsed.setdefault("_status", "SUCCESS")
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return {"text": result_text, "_status": "SUCCESS"}


def aws_mcp_client() -> AwsMCPClient:
    return AwsMCPClient.instance()
