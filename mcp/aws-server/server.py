from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("aws-mcp")

from audit import AuditRecord, audit_logger
from policy import (
    authorize_and_validate,
    IAM_LEAST_PRIVILEGE_NOTES,
    PolicyError,
    ToolPolicy,
    TOOL_POLICIES,
)
from services.aws_services import (
    cloudwatch_service,
    deployment_service,
    health_service,
    metrics_service,
)

_MCP_AVAILABLE = True
try:
    from mcp.server.fastmcp import FastMCP, Context
except Exception as e:  # pragma: no cover
    _MCP_AVAILABLE = False
    logger.warning("MCP SDK unavailable: %s. Running standalone only.", e)

    class Context:  # type: ignore[no-redef]
        @property
        def meta(self) -> Dict[str, Any]:
            return {}


SERVER_NAME = "aws-mcp"
SERVER_VERSION = "0.1.0"


def _extract_context(ctx: Any) -> tuple[str, str]:
    meta: Dict[str, Any] = {}
    try:
        meta = dict(getattr(ctx, "meta", {}) or {})
    except Exception:
        meta = {}
    tenant_id = str(
        meta.get("tenant_id")
        or meta.get("tenant")
        or os.environ.get("MCP_DEFAULT_TENANT_ID", "demo")
    ).strip()
    agent_name = str(
        meta.get("agent_name")
        or meta.get("agent")
        or os.environ.get("MCP_DEFAULT_AGENT_NAME", "rca-agent")
    ).strip()
    return tenant_id, agent_name


def _run_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    ctx: Any,
    impl_fn,
) -> str:
    started_at = time.monotonic()
    tenant_id, agent_name = _extract_context(ctx)
    status = "SUCCESS"
    output: Dict[str, Any] = {}
    try:
        agent_clean, tenant_clean, policy, validated = authorize_and_validate(
            tool_name=tool_name,
            agent_name=agent_name,
            tenant_id=tenant_id,
            inputs=arguments,
        )
    except PolicyError as e:
        duration_ms = max(1, int((time.monotonic() - started_at) * 1000))
        output = {"error": str(e), "error_type": type(e).__name__}
        audit_logger().record(
            AuditRecord(
                tool_name=tool_name,
                agent_name=agent_name or "unknown",
                tenant_id=tenant_id or "unknown",
                input_data=arguments,
                output_data=output,
                status="POLICY_DENIED",
                duration_ms=duration_ms,
                started_at=time.time(),
            )
        )
        return json.dumps(output, indent=2, sort_keys=True)

    try:
        output = impl_fn(**validated)
    except Exception as e:
        status = "FAILED"
        output = {"error": str(e), "error_type": type(e).__name__}
        logger.exception("AWS MCP tool failed: %s", tool_name)

    duration_ms = max(1, int((time.monotonic() - started_at) * 1000))
    audit_logger().record(
        AuditRecord(
            tool_name=tool_name,
            agent_name=agent_clean,
            tenant_id=tenant_clean,
            input_data=validated,
            output_data=output if isinstance(output, dict) else {"result": output},
            status=status,
            duration_ms=duration_ms,
            started_at=time.time(),
        )
    )
    return json.dumps(output, indent=2, sort_keys=True, default=str)


def _build_server():
    if not _MCP_AVAILABLE:
        return None
    mcp = FastMCP(
        SERVER_NAME,
        version=SERVER_VERSION,
        description=(
            "AWS MCP server providing read-only access to CloudWatch logs, operational "
            "metrics, deployment metadata, and ECS/service health. Least-privilege IAM, "
            "per-tenant rate limits, input validation, and audit logging."
        ),
    )

    @mcp.tool(name="get_cloudwatch_logs")
    def get_cloudwatch_logs(
        service: str,
        minutes: int = 30,
        limit: int = 200,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        Retrieve application logs from AWS CloudWatch Logs for a specific service.

        Use this when investigating application failures, exceptions, timeout behavior,
        or unusual service activity. The window is bounded to 1-120 minutes to prevent
        unbounded log retrieval. Results are chronologically ordered with a level-count
        summary and a safe maximum row limit.

        Args:
            service: Service name, e.g. payment-service
            minutes: How far back to query logs (1-120, default 30)
            limit: Maximum log entries to return (capped at 200)
        """
        def impl(**kw):
            svc = cloudwatch_service()
            return svc.get_logs(
                service=kw["service"], minutes=kw["minutes"], max_items=kw.get("limit", 200)
            )
        return _run_tool("get_cloudwatch_logs", {"service": service, "minutes": minutes, "limit": limit}, ctx, impl)

    @mcp.tool(name="get_service_metrics")
    def get_service_metrics(
        service: str,
        window_minutes: int = 30,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        Retrieve a structured summary of key operational metrics for a service.

        Metrics include: error_rate %, p95/p50 latency, request count/rate, CPU %,
        memory %, and DB connection pool utilization, with deltas vs previous window
        to make regressions obvious. Use this to quantify incident severity and
        correlate symptom onset with changes in load or saturation.

        Args:
            service: Service name, e.g. payment-service
            window_minutes: Aggregation window in minutes (1-360, default 30)
        """
        def impl(**kw):
            return metrics_service().get_metrics(
                service=kw["service"], window_minutes=kw["window_minutes"]
            )
        return _run_tool("get_service_metrics", {"service": service, "window_minutes": window_minutes}, ctx, impl)

    @mcp.tool(name="get_recent_deployment")
    def get_recent_deployment(
        service: str,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        Retrieve metadata about the most recent production deployment for a service.

        Returns semantic version, deployment timestamp, previous version, commit SHA,
        deploying actor, and overall status. Use this to answer the question: "did a
        release immediately precede the onset of the incident symptoms?"

        Args:
            service: Service name, e.g. payment-service
        """
        def impl(**kw):
            return deployment_service().get_recent(service=kw["service"])
        return _run_tool("get_recent_deployment", {"service": service}, ctx, impl)

    @mcp.tool(name="get_service_health")
    def get_service_health(
        service: str,
        ctx: Context = None,  # type: ignore[assignment]
    ) -> str:
        """
        High-level service health snapshot.

        Returns overall status (HEALTHY/DEGRADED/UNHEALTHY), healthy vs unhealthy
        instance counts, desired capacity, and aggregate health percent. Use as a
        first-pass signal to understand blast radius before diving into logs/metrics.

        Args:
            service: Service name, e.g. payment-service
        """
        def impl(**kw):
            return health_service().get_health(service=kw["service"])
        return _run_tool("get_service_health", {"service": service}, ctx, impl)

    @mcp.resource("deployments://{service}")
    def deployment_resource(service: str) -> str:
        """
        Resource URI for a service's most recent deployment.
        Example: deployments://payment-service
        """
        rec = deployment_service().get_recent(service)
        return (
            f"# Deployment — {rec.get('service', service)}\n\n"
            f"- **Version:** {rec.get('version')}\n"
            f"- **Deployed At:** {rec.get('deployed_at')}\n"
            f"- **Previous:** {rec.get('previous_version')}\n"
            f"- **Deployed By:** {rec.get('deployed_by')}\n"
            f"- **Commit:** `{rec.get('commit_sha', 'N/A')}`\n"
            f"- **Status:** {rec.get('status')}\n"
        )

    @mcp.resource("metrics://{service}")
    def metrics_resource(service: str) -> str:
        """Resource URI for a service's current metrics snapshot."""
        rec = metrics_service().get_metrics(service, window_minutes=30)
        m = rec.get("metrics", {})
        return (
            f"# Metrics Snapshot — {rec.get('service', service)}\n\n"
            f"- **Error Rate:** {m.get('error_rate')}% (Δ {m.get('error_rate_delta_vs_previous')}pp)\n"
            f"- **Latency p95:** {m.get('latency_p95_ms')}ms (Δ {m.get('latency_p95_delta_vs_previous')}ms)\n"
            f"- **CPU:** {m.get('cpu_percent')}%\n"
            f"- **Memory:** {m.get('memory_percent')}%\n"
            f"- **Request Count:** {m.get('request_count')}\n"
        )

    @mcp.prompt(name="aws-incident-triage")
    def aws_incident_triage(service: str = "the affected service") -> str:
        """
        Standardized AWS triage prompt template. Use at the beginning of any
        AWS-related investigation to ensure the agent checks all four evidence
        sources in a consistent order.
        """
        return f"""## AWS Evidence Triage Protocol for {service}

Step 1: Load resources
- Load deployments://{service} resource
- Load metrics://{service} resource

Step 2: Call tools in this order
1. get_service_health(service="{service}")
2. get_service_metrics(service="{service}", window_minutes=60)
3. get_cloudwatch_logs(service="{service}", minutes=60)
4. get_recent_deployment(service="{service}")

Step 3: Correlate
- Compare deployment timestamp vs metric inflection timestamp
- Extract stack traces / exception names from logs
- Summarize health status and instance counts

Step 4: Report
Return the evidence as structured items with source=cloudwatch/metrics/deployment/health.
"""
    return mcp


def run_standalone_test() -> int:
    print("=" * 70)
    print(f"AWS MCP Server v{SERVER_VERSION} — STANDALONE TEST MODE")
    print("=" * 70)
    print()
    tests = [
        ("1. get_service_health('payment-service')", "get_service_health", {"service": "payment-service"}),
        ("2. get_service_metrics('payment-service', 30)", "get_service_metrics", {"service": "payment-service", "window_minutes": 30}),
        ("3. get_recent_deployment('payment-service')", "get_recent_deployment", {"service": "payment-service"}),
        ("4. get_cloudwatch_logs('payment-service', minutes=60, limit=20)", "get_cloudwatch_logs", {"service": "payment-service", "minutes": 60, "limit": 20}),
        ("5. get_cloudwatch_logs with minutes too big -> bounded", "get_cloudwatch_logs", {"service": "payment-service", "minutes": 9999, "limit": 20}),
        ("6. Input validation: empty service", "get_service_health", {"service": ""}),
        ("7. Unknown service: 'nonexistent' uses fallback mock", "get_service_metrics", {"service": "nonexistent", "window_minutes": 10}),
    ]
    all_ok = True
    for label, tool_name, args in tests:
        print(f"--- {label}")
        started = time.monotonic()
        tenant_id = "demo"
        agent_name = "rca-agent"
        status_out = "SUCCESS"
        try:
            a_clean, t_clean, policy, validated = authorize_and_validate(
                tool_name, agent_name, tenant_id, args
            )
        except PolicyError as e:
            dur_ms = max(1, int((time.monotonic() - started) * 1000))
            print(f"   EXPECTED POLICY — status=POLICY_DENIED duration_ms={dur_ms} error={e!r}")
            audit_logger().record(AuditRecord(
                tool_name=tool_name, agent_name=agent_name, tenant_id=tenant_id,
                input_data=args, output_data={"error": str(e)}, status="POLICY_DENIED",
                duration_ms=dur_ms, started_at=time.time(),
            ))
            continue

        try:
            if tool_name == "get_service_health":
                result = health_service().get_health(validated["service"])
            elif tool_name == "get_service_metrics":
                result = metrics_service().get_metrics(validated["service"], validated["window_minutes"])
            elif tool_name == "get_recent_deployment":
                result = deployment_service().get_recent(validated["service"])
            elif tool_name == "get_cloudwatch_logs":
                result = cloudwatch_service().get_logs(validated["service"], validated["minutes"], validated.get("limit", 200))
            else:
                raise ValueError(f"Unknown {tool_name}")
        except Exception as e:
            status_out = "FAILED"
            result = {"error": str(e), "error_type": type(e).__name__}
            all_ok = False
        dur_ms = max(1, int((time.monotonic() - started) * 1000))
        audit_logger().record(AuditRecord(
            tool_name=tool_name, agent_name=a_clean, tenant_id=t_clean,
            input_data=validated, output_data=result if isinstance(result, dict) else {"r": result},
            status=status_out, duration_ms=dur_ms, started_at=time.time(),
        ))
        if isinstance(result, dict):
            summary_parts = []
            for k in ["status", "version", "deployed_at", "total_returned", "log_level_counts", "metrics", "health_percent"]:
                if k in result:
                    v = result[k]
                    if isinstance(v, dict):
                        v = {kk: vv for kk, vv in list(v.items())[:3]}
                    summary_parts.append(f"{k}={v}")
            print(f"   OK status={status_out} duration_ms={dur_ms} {' '.join(summary_parts)}")
        else:
            print(f"   OK status={status_out} duration_ms={dur_ms}")
        print()
    print("IAM Least-Privilege Note: Investigation role =", IAM_LEAST_PRIVILEGE_NOTES["investigation_role"][:4], "...")
    print("=" * 70)
    print("ALL AWS STANDALONE TESTS PASSED" if all_ok else "SOME AWS TESTS FAILED")
    return 0 if all_ok else 1


def print_capabilities() -> None:
    print("=" * 70)
    print(f"AWS MCP Server v{SERVER_VERSION} Capabilities")
    print("=" * 70)
    print("TOOLS:")
    for name, pol in TOOL_POLICIES.items():
        print(f"  - {name:<30s} perm={pol.permission.value} rate={pol.rate_limit_per_minute}/min timeout={pol.timeout_seconds}s")
    print("RESOURCES:")
    print("  - deployments://{service}    Latest deployment summary")
    print("  - metrics://{service}        Key metrics snapshot")
    print("PROMPTS:")
    print("  - aws-incident-triage        Standardized AWS evidence workflow")
    print("IAM:")
    print("  - Investigation role:", ", ".join(IAM_LEAST_PRIVILEGE_NOTES["investigation_role"][:5]), "...")
    print("  - Forbidden:", ", ".join(IAM_LEAST_PRIVILEGE_NOTES["forbidden"]))
    print("=" * 70)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--capabilities" in argv or "-c" in argv:
        print_capabilities()
        return 0
    if "--test" in argv or "--standalone" in argv or "-t" in argv:
        return run_standalone_test()
    if not _MCP_AVAILABLE:
        print("ERROR: MCP SDK not installed. Run `pip install mcp[cli]` or use --test", file=sys.stderr)
        return 2
    server = _build_server()
    try:
        server.run()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
