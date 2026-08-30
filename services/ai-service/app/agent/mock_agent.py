"""
Mock LLM client for local development without API credits.
"""

import json
import logging
from datetime import datetime, timezone
from app.tools.incident import get_incident
from app.tools.logs import get_logs
from app.tools.deployment import get_recent_deployment
from app.tools.metrics import get_metrics
from app.tools.policy import authorize_tool
from app.models.incident import RCAResponse, ToolExecutionRecord

logger = logging.getLogger(__name__)


def run_mock_investigation(incident_id: str) -> RCAResponse:
    """
    Execute the full agent investigation loop using mock tool data and return observability.
    """
    logger.info("[MOCK AGENT] Starting investigation for %s", incident_id)
    tool_executions = []

    # Helper to track execution
    def run_tool_tracked(name: str, fn, **kwargs):
        start = datetime.now(timezone.utc)
        status = "SUCCESS"
        result = {}
        try:
            assert authorize_tool(name)
            result = fn(**kwargs)
        except Exception as e:
            status = "FAILED"
            result = {"error": str(e)}

        end = datetime.now(timezone.utc)
        duration = int((end - start).total_seconds() * 1000)
        tool_executions.append(
            ToolExecutionRecord(
                tool_name=name,
                input=json.dumps(kwargs),
                output=json.dumps(result),
                status=status,
                started_at=start.isoformat(),
                completed_at=end.isoformat(),
                duration_ms=max(1, duration),
            )
        )
        return result

    # Step 1: get_incident
    incident = run_tool_tracked("get_incident", get_incident, incident_id=incident_id)
    service = incident.get("service", "unknown")

    # Step 2: get_logs
    logs = run_tool_tracked("get_logs", get_logs, service=service, minutes=30)

    # Step 3: get_metrics
    metrics = run_tool_tracked("get_metrics", get_metrics, service=service)

    # Step 4: get_recent_deployment
    deployment = run_tool_tracked(
        "get_recent_deployment", get_recent_deployment, service=service
    )

    # Synthesize RCA
    timeout_errors = [
        l for l in logs.get("logs", []) if "Timeout" in l or "timeout" in l
    ]

    return RCAResponse(
        incident_id=incident_id,
        service=service,
        summary=(
            f"Error rate spiked from {metrics.get('error_rate_before', '1.2%')} to "
            f"{metrics.get('error_rate_current', '18%')} shortly after {deployment.get('version', 'v2.4.1')} deployment."
        ),
        root_cause=(
            f"A regression introduced in deployment {deployment.get('version', 'v2.4.1')} "
            f"(deployed at {deployment.get('deployed_at', '')}) is causing repeated "
            f"PaymentTimeoutException errors. The deployment occurred 4 minutes before "
            f"the incident started. Database connection timeouts are also observed, "
            f"suggesting a connection pool or timeout configuration change in the new version."
        ),
        confidence=0.91,
        evidence=[
            f"Error rate increased from {metrics.get('error_rate_before', '1.2%')} to {metrics.get('error_rate_current', '18%')}",
            f"Latency (p99) degraded from {metrics.get('latency_p99_before', '180ms')} to {metrics.get('latency_p99_current', '920ms')}",
            f"Incident started at {incident.get('started_at', '')}, deployment {deployment.get('version', '')} at {deployment.get('deployed_at', '')} (4 min prior)",
            f"{len(timeout_errors)} timeout-related errors found in {logs.get('minutes', 30)}-minute log window",
            "CPU (54%) and memory (61%) are within normal range — infrastructure not the cause",
        ],
        recommended_actions=[
            f"Review timeout-related code changes introduced in {deployment.get('version', '')} vs {deployment.get('previous_version', '')}",
            f"Consider rollback to {deployment.get('previous_version', '')} if root cause confirmed",
            "Check connection pool configuration changes in the new deployment",
            "Monitor error rate after rollback to confirm resolution",
        ],
        actions_executed=[],
        # Observability
        input_tokens=1250,
        output_tokens=350,
        tool_calls=4,
        tool_executions=tool_executions,
    )
