from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Deque, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PermissionLevel(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    HIGH_RISK = "HIGH_RISK"
    CRITICAL = "CRITICAL"
    DENY = "DENY"


@dataclass(frozen=True)
class ToolPolicy:
    permission: PermissionLevel
    description: str
    rate_limit_per_minute: int
    timeout_seconds: int
    max_minutes_window: int = 360
    max_service_length: int = 100
    max_query_length: int = 500
    max_result_limit: int = 200


TOOL_POLICIES: Dict[str, ToolPolicy] = {
    "get_cloudwatch_logs": ToolPolicy(
        permission=PermissionLevel.READ,
        description=(
            "Retrieve application logs from AWS CloudWatch Logs for a specified service "
            "within a bounded time window. Use when investigating application failures, "
            "exceptions, timeout behavior, or unusual service behavior. Results are "
            "chronologically ordered and truncated at a safe maximum size to avoid "
            "overwhelming the agent context."
        ),
        rate_limit_per_minute=15,
        timeout_seconds=5,
        max_minutes_window=120,
    ),
    "get_service_metrics": ToolPolicy(
        permission=PermissionLevel.READ,
        description=(
            "Retrieve a structured summary of key operational metrics for a service: "
            "error rate percentage, p95/p50 latency in milliseconds, request count, "
            "CPU utilization percent, and memory utilization percent. Use this to "
            "quantify incident severity and correlate symptoms with load or saturation."
        ),
        rate_limit_per_minute=30,
        timeout_seconds=5,
        max_minutes_window=360,
    ),
    "get_recent_deployment": ToolPolicy(
        permission=PermissionLevel.READ,
        description=(
            "Retrieve metadata about the most recent production deployment for a given "
            "service: semantic version, timestamp of deployment, previous version, "
            "and deploying commit/author. Use this to check whether a code or config "
            "release immediately preceded the onset of incident symptoms."
        ),
        rate_limit_per_minute=30,
        timeout_seconds=3,
    ),
    "get_service_health": ToolPolicy(
        permission=PermissionLevel.READ,
        description=(
            "Return high-level service health: overall status (HEALTHY/DEGRADED/UNHEALTHY), "
            "count of healthy vs unhealthy ECS instances or Kubernetes pods. Use as a "
            "first-pass signal to understand blast radius before diving into logs/metrics."
        ),
        rate_limit_per_minute=60,
        timeout_seconds=3,
    ),
}


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    def check(self, key: Tuple[str, str], limit: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) < limit:
            bucket.append(now)
            return True
        return False


_rate_limiter = RateLimiter()


class PolicyEngine:
    _ALLOWED_AGENTS = {"rca-agent", "supervisor-agent", "research-agent", "investigation-agent", "default"}

    def authenticate_agent(self, agent_name: Optional[str]) -> str:
        name = (agent_name or "default").strip() or "default"
        if name not in self._ALLOWED_AGENTS:
            raise PermissionError(f"Agent '{name}' is not authorized for AWS MCP")
        return name

    def authorize_tool(self, tool_name: str) -> ToolPolicy:
        policy = TOOL_POLICIES.get(tool_name)
        if policy is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        if policy.permission == PermissionLevel.DENY:
            raise PermissionError(f"Tool '{tool_name}' is disabled by policy")
        return policy

    def check_rate_limit(self, tool_name: str, tenant_id: str, policy: ToolPolicy) -> None:
        key = (tool_name, tenant_id)
        if not _rate_limiter.check(key, policy.rate_limit_per_minute):
            raise RateLimitError(
                f"Rate limit exceeded for '{tool_name}' / tenant '{tenant_id}': "
                f">{policy.rate_limit_per_minute}/min"
            )

    def validate_inputs(self, tool_name: str, policy: ToolPolicy, inputs: Dict[str, Any]) -> Dict[str, Any]:
        cleaned: Dict[str, Any] = {}
        if "service" in inputs:
            value = str(inputs["service"]).strip()
            if not value:
                raise ValidationError("service cannot be empty")
            if len(value) > policy.max_service_length:
                raise ValidationError(f"service name too long ({policy.max_service_length} max)")
            if not all(c.isalnum() or c in "-_" for c in value):
                raise ValidationError("service contains invalid characters")
            cleaned["service"] = value

        if "minutes" in inputs:
            try:
                value = int(inputs["minutes"])
            except (TypeError, ValueError):
                raise ValidationError("minutes must be an integer")
            if value < 1:
                raise ValidationError("minutes must be >= 1")
            if value > policy.max_minutes_window:
                value = policy.max_minutes_window
            cleaned["minutes"] = value

        if "window_minutes" in inputs:
            try:
                value = int(inputs["window_minutes"])
            except (TypeError, ValueError):
                raise ValidationError("window_minutes must be an integer")
            if value < 1:
                raise ValidationError("window_minutes must be >= 1")
            if value > policy.max_minutes_window:
                value = policy.max_minutes_window
            cleaned["window_minutes"] = value

        if "limit" in inputs:
            try:
                value = int(inputs["limit"])
            except (TypeError, ValueError):
                raise ValidationError("limit must be an integer")
            value = max(1, min(value, policy.max_result_limit))
            cleaned["limit"] = value

        return cleaned


class PolicyError(Exception):
    pass


class PermissionError(PolicyError):
    pass


class ValidationError(PolicyError):
    pass


class RateLimitError(PolicyError):
    pass


_policy_engine = PolicyEngine()


def policy_engine() -> PolicyEngine:
    return _policy_engine


def authorize_and_validate(
    tool_name: str,
    agent_name: Optional[str],
    tenant_id: Optional[str],
    inputs: Dict[str, Any],
) -> Tuple[str, str, ToolPolicy, Dict[str, Any]]:
    engine = policy_engine()
    if not tenant_id:
        raise ValidationError("tenant_id is required in the security context")
    tenant_clean = str(tenant_id).strip()
    if not tenant_clean:
        raise ValidationError("tenant_id cannot be empty")
    agent_clean = engine.authenticate_agent(agent_name)
    policy = engine.authorize_tool(tool_name)
    engine.check_rate_limit(tool_name, tenant_clean, policy)
    validated = engine.validate_inputs(tool_name, policy, dict(inputs or {}))
    return agent_clean, tenant_clean, policy, validated


IAM_LEAST_PRIVILEGE_NOTES = {
    "investigation_role": [
        "logs:DescribeLogGroups",
        "logs:FilterLogEvents",
        "logs:GetLogEvents",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:GetMetricData",
        "ecs:DescribeServices",
        "ecs:DescribeTasks",
        "ecs:ListTasks",
        "codedeploy:GetDeployment",
        "codedeploy:ListDeployments",
    ],
    "forbidden": [
        "logs:PutLogEvents",
        "ecs:UpdateService",
        "ecs:StopTask",
        "codedeploy:CreateDeployment",
        "iam:*",
        "*:*",
    ],
}
