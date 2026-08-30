from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MCP_GITHUB_SERVER_DIR = Path(__file__).resolve().parents[3] / "mcp" / "github-server"
MCP_USE_LOCAL = os.environ.get("MCP_USE_LOCAL", "true").lower() in ("1", "true", "yes")

_MCP_SDK_AVAILABLE = False
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    _MCP_SDK_AVAILABLE = True
except Exception as e:
    logger.info("MCP SDK not available for GitHub client: %s. Using local in-process mode.", e)


_adapter_instance = None


def _load_adapter():
    global _adapter_instance
    if _adapter_instance is not None:
        return
    if str(MCP_GITHUB_SERVER_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_GITHUB_SERVER_DIR))
    try:
        from github_adapter import GitHubAdapter
        _adapter_instance = GitHubAdapter()
    except Exception as e:
        logger.warning("Could not load GitHub adapter: %s", e)


class GithubMCPClient:
    _instance: Optional["GithubMCPClient"] = None

    def __init__(self, default_agent: str = "rca-agent", default_tenant: str = "demo"):
        self._default_agent = default_agent
        self._default_tenant = default_tenant
        self._use_local = MCP_USE_LOCAL or not _MCP_SDK_AVAILABLE

    @classmethod
    def instance(cls) -> "GithubMCPClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ctx(self, tenant_id, agent_name):
        tenant = (tenant_id or self._default_tenant or "demo").strip() or "demo"
        agent = (agent_name or self._default_agent or "rca-agent").strip() or "rca-agent"
        return tenant, agent

    def _call_local(self, tool_name, arguments):
        _load_adapter()
        if _adapter_instance is None:
            return {"error": "GitHub MCP local adapter unavailable", "error_type": "ImportError"}
        try:
            if tool_name == "search_code":
                repository = arguments["repository"]
                query = arguments["query"]
                limit = int(arguments.get("limit", 20))
                if limit < 1:
                    limit = 20
                results = _adapter_instance.search_code(repository, query, limit)
                return {"repository": repository, "query": query, "total_returned": len(results), "results": results}
            if tool_name == "get_recent_commits":
                repository = arguments["repository"]
                branch = str(arguments.get("branch", "main") or "main")
                limit = int(arguments.get("limit", 10))
                if limit < 1:
                    limit = 10
                commits = _adapter_instance.get_recent_commits(repository, branch, limit)
                return {"repository": repository, "branch": branch, "total_returned": len(commits), "commits": commits}
            if tool_name == "get_pull_request":
                repository = arguments["repository"]
                number = int(arguments["number"])
                pr = _adapter_instance.get_pull_request(repository, number)
                if pr is None:
                    return {"repository": repository, "number": number, "pull_request": None, "message": "Not found"}
                return {"repository": repository, "number": number, "pull_request": pr}
            if tool_name == "get_file":
                repository = arguments["repository"]
                file_path = arguments["file_path"]
                ref = str(arguments.get("ref", "main") or "main")
                f = _adapter_instance.get_file(repository, file_path, ref)
                if f is None:
                    return {"repository": repository, "file_path": file_path, "ref": ref, "file": None, "message": "Not found"}
                return {"repository": repository, "file_path": file_path, "ref": ref, "file": f}
        except Exception as e:
            logger.exception("GitHub MCP local call failed tool=%s", tool_name)
            return {"error": str(e), "error_type": type(e).__name__}
        return {"error": f"Unknown GitHub tool: {tool_name}", "error_type": "UnknownTool"}

    def call_tool(self, tool_name, arguments, tenant_id=None, agent_name=None):
        _tenant, _agent = self._ctx(tenant_id, agent_name)
        if self._use_local:
            return self._call_local(tool_name, arguments)
        return self._call_stdio(tool_name, arguments, _tenant, _agent)

    def _call_stdio(self, tool_name, arguments, tenant, agent):
        if not _MCP_SDK_AVAILABLE:
            return {"error": "MCP SDK not installed", "error_type": "MissingMcpSdk"}
        server_script = str(MCP_GITHUB_SERVER_DIR / "server.py")
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
            logger.exception("GitHub MCP stdio call failed tool %s", tool_name)
            return {"error": f"MCP stdio failed: {e}", "error_type": type(e).__name__, "_status": "FAILED"}
        try:
            parsed = json.loads(result_text)
            if isinstance(parsed, dict):
                parsed.setdefault("_status", "SUCCESS")
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return {"text": result_text, "_status": "SUCCESS"}


def github_mcp_client() -> GithubMCPClient:
    return GithubMCPClient.instance()
