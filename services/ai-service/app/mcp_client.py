from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)

MCP_POSTGRES_SERVER_DIR = Path(__file__).resolve().parents[3] / "mcp" / "postgres-server"
MCP_USE_LOCAL = os.environ.get("MCP_USE_LOCAL", "true").lower() in ("1", "true", "yes")

_MCP_SDK_AVAILABLE = False
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_SDK_AVAILABLE = True
except Exception as e:  # pragma: no cover
    logger.info("MCP SDK not available for client mode: %s. Using local in-process mode.", e)
    _MCP_SDK_AVAILABLE = False

_LOCAL_TOOLS_AVAILABLE = False
_local_execute_tool = None
try:
    if str(MCP_POSTGRES_SERVER_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_POSTGRES_SERVER_DIR))
    from tools import execute_tool as _local_execute_tool_fn  # type: ignore
    _local_execute_tool = _local_execute_tool_fn
    _LOCAL_TOOLS_AVAILABLE = True
except Exception as e:
    logger.warning(
        "Could not load local MCP server tools module (%s). Ensure mcp/postgres-server is accessible.",
        e,
    )
    _LOCAL_TOOLS_AVAILABLE = False


class PostgresMCPClient:
    """
    Adapter for calling PostgreSQL MCP server tools from the LangGraph agent.

    Supports two modes:
      1. Local in-process mode (default): imports `execute_tool` directly from the
         MCP server's `tools.py` module. No subprocess, no serialization overhead,
         works even when the `mcp` Python SDK is not installed. Policy, rate limits,
         input validation, tenant isolation, and audit logging all still apply.

      2. MCP SDK stdio mode: uses the official MCP SDK `ClientSession` over stdio
         to talk to the MCP server as a separate subprocess. Requires `mcp` package
         and the server to be installed/executable. Enabled by setting env var
         `MCP_USE_LOCAL=false`.
    """

    _instance: Optional["PostgresMCPClient"] = None

    def __init__(self, default_agent: str = "rca-agent", default_tenant: str = "demo"):
        self._default_agent = default_agent
        self._default_tenant = default_tenant
        self._use_local = MCP_USE_LOCAL or not _MCP_SDK_AVAILABLE
        if self._use_local and not _LOCAL_TOOLS_AVAILABLE:
            raise RuntimeError(
                "PostgreSQL MCP local tools module is unavailable and MCP SDK "
                "stdio mode is also unavailable. Check mcp/postgres-server/tools.py "
                "or install the MCP SDK with: pip install mcp[cli]"
            )

    @classmethod
    def instance(cls) -> "PostgresMCPClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _security_context(
        self, tenant_id: Optional[str], agent_name: Optional[str]
    ) -> Tuple[str, str]:
        tenant = (tenant_id or self._default_tenant or "demo").strip() or "demo"
        agent = (agent_name or self._default_agent or "rca-agent").strip() or "rca-agent"
        return tenant, agent

    def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tenant_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        tenant, agent = self._security_context(tenant_id, agent_name)
        if self._use_local:
            return self._call_local(tool_name, arguments, tenant, agent)
        return self._call_stdio(tool_name, arguments, tenant, agent)

    def _call_local(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tenant_id: str,
        agent_name: str,
    ) -> Dict[str, Any]:
        assert _local_execute_tool is not None
        result = _local_execute_tool(
            tool_name=tool_name,
            arguments=arguments,
            agent_name=agent_name,
            tenant_id=tenant_id,
        )
        output = dict(result.output or {})
        output.setdefault("_status", result.status)
        output.setdefault("_duration_ms", result.duration_ms)
        if result.error:
            output.setdefault("_error", result.error)
        return output

    def _call_stdio(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        tenant_id: str,
        agent_name: str,
    ) -> Dict[str, Any]:
        if not _MCP_SDK_AVAILABLE:
            raise RuntimeError(
                "MCP SDK not installed. Install with: pip install mcp[cli], "
                "or enable local mode with MCP_USE_LOCAL=true."
            )

        server_script = str(MCP_POSTGRES_SERVER_DIR / "server.py")
        if not os.path.exists(server_script):
            raise FileNotFoundError(f"MCP server script not found: {server_script}")

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
            env={
                **os.environ,
                "MCP_DEFAULT_TENANT_ID": tenant_id,
                "MCP_DEFAULT_AGENT_NAME": agent_name,
                "MCP_USE_MOCK": os.environ.get("MCP_USE_MOCK", "true"),
            },
        )

        result_text = ""
        try:
            with stdio_client(server_params) as (read, write):
                with ClientSession(read, write) as session:
                    session.initialize()
                    call_result = session.call_tool(
                        tool_name,
                        arguments,
                    )
                    parts = getattr(call_result, "content", []) or []
                    if parts:
                        first = parts[0]
                        result_text = str(getattr(first, "text", "") or "")
                    else:
                        result_text = str(call_result)
        except Exception as e:
            logger.exception("MCP stdio call failed for tool %s", tool_name)
            return {
                "error": f"MCP stdio call failed: {e}",
                "error_type": type(e).__name__,
                "_status": "FAILED",
            }

        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, dict):
                parsed.setdefault("_status", "SUCCESS")
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return {"text": result_text, "_status": "SUCCESS"}


def mcp_client() -> PostgresMCPClient:
    return PostgresMCPClient.instance()


def call_mcp_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    tenant_id: Optional[str] = None,
    agent_name: Optional[str] = None,
) -> Dict[str, Any]:
    return mcp_client().call_tool(tool_name, arguments, tenant_id=tenant_id, agent_name=agent_name)
