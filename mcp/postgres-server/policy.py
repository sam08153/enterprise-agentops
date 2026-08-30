from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, Optional, Tuple

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
    max_query_length: int = 500
    max_result_limit: int = 20
    min_minutes: Optional[int] = None
    max_minutes: Optional[int] = None
    max_id_length: int = 100
    max_service_length: int = 100


TOOL_POLICIES: Dict[str, ToolPolicy] = {
    "get_incident": ToolPolicy(
        permission=PermissionLevel.READ,
        description="Retrieve a single incident by its identifier. Returns full incident metadata including severity, status, description, affected service, and timeline. Use when you need detailed information about a specific known incident.",
        rate_limit_per_minute=60,
        max_id_length=100,
    ),
    "search_incidents": ToolPolicy(
        permission=PermissionLevel.READ,
        description="Search across historical and active incidents using a free-text query against incident titles, descriptions, services, and severities. Returns the most relevant matching incidents ordered by recency and relevance. Use when investigating patterns, looking for similar past incidents, or discovering incidents related to a specific service or failure mode.",
        rate_limit_per_minute=20,
        max_query_length=500,
        max_result_limit=20,
    ),
    "get_incident_history": ToolPolicy(
        permission=PermissionLevel.READ,
        description="Retrieve the full incident history for a specific service. Returns all incidents that have affected the given service, ordered by recency. Use when performing root cause analysis and you need to understand recurring failure patterns, seasonal issues, or service-specific incident trends.",
        rate_limit_per_minute=30,
        max_service_length=100,
        max_result_limit=20,
    ),
    "search_documents": ToolPolicy(
        permission=PermissionLevel.READ,
        description="Search organizational knowledge documents including runbooks, architecture docs, postmortems, and standard operating procedures. Uses keyword matching across document titles, content, and sources. Use when looking for documented procedures, architectural context, known issues, or remediation playbooks.",
        rate_limit_per_minute=20,
        max_query_length=500,
        max_result_limit=20,
    ),
    "get_document": ToolPolicy(
        permission=PermissionLevel.READ,
        description="Retrieve a single full document by its identifier or source path. Returns the complete document content including title, body, source, and creation metadata. Use when you have found a relevant document summary from search_documents and need to read the full content for detailed operational guidance or architectural context.",
        rate_limit_per_minute=60,
        max_id_length=200,
    ),
}


class RateLimiter:
    def __init__(self) -> None:
        self._buckets: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    def check(self, key: Tuple[str, str], limit: int, window_seconds: int = 60) -> Tuple[bool, int, int]:
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        current = len(bucket)
        if current < limit:
            bucket.append(now)
            return True, current + 1, limit
        return False, current, limit

    def remaining(self, key: Tuple[str, str], limit: int, window_seconds: int = 60) -> int:
        now = time.monotonic()
        bucket = self._buckets[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        return max(0, limit - len(bucket))


_rate_limiter = RateLimiter()


def rate_limiter() -> RateLimiter:
    return _rate_limiter


class PolicyEngine:
    def __init__(self) -> None:
        self._allowed_agents: set[str] = {
            "rca-agent",
            "supervisor-agent",
            "research-agent",
            "investigation-agent",
            "default",
        }

    def authenticate_agent(self, agent_name: Optional[str]) -> str:
        name = (agent_name or "default").strip() or "default"
        if name not in self._allowed_agents:
            raise PermissionError(f"Agent '{name}' is not authorized to access this MCP server")
        return name

    def authorize_tool(self, tool_name: str, agent_name: str) -> ToolPolicy:
        policy = TOOL_POLICIES.get(tool_name)
        if policy is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        if policy.permission == PermissionLevel.DENY:
            raise PermissionError(f"Tool '{tool_name}' is disabled")
        return policy

    def check_rate_limit(self, tool_name: str, tenant_id: str, policy: ToolPolicy) -> None:
        key = (tool_name, tenant_id)
        allowed, current, limit = _rate_limiter.check(key, policy.rate_limit_per_minute)
        if not allowed:
            raise RateLimitError(
                f"Rate limit exceeded for tool '{tool_name}' in tenant '{tenant_id}': "
                f"{current}/{limit} requests per minute"
            )

    def validate_inputs(self, tool_name: str, policy: ToolPolicy, inputs: Dict[str, Any]) -> Dict[str, Any]:
        cleaned: Dict[str, Any] = {}

        if "incident_id" in inputs:
            value = str(inputs["incident_id"]).strip()
            if not value:
                raise ValidationError("incident_id cannot be empty")
            if len(value) > policy.max_id_length:
                raise ValidationError(
                    f"incident_id exceeds maximum length of {policy.max_id_length}"
                )
            cleaned["incident_id"] = value

        if "document_id" in inputs:
            value = str(inputs["document_id"]).strip()
            if not value:
                raise ValidationError("document_id cannot be empty")
            if len(value) > 200:
                raise ValidationError("document_id exceeds maximum length of 200")
            cleaned["document_id"] = value

        if "query" in inputs:
            value = str(inputs["query"]).strip()
            if not value:
                raise ValidationError("query cannot be empty")
            if len(value) > policy.max_query_length:
                raise ValidationError(
                    f"query exceeds maximum length of {policy.max_query_length} characters"
                )
            if any(c in value for c in ["\x00"]):
                raise ValidationError("query contains invalid characters")
            cleaned["query"] = value

        if "service" in inputs:
            value = str(inputs["service"]).strip()
            if not value:
                raise ValidationError("service cannot be empty")
            if len(value) > policy.max_service_length:
                raise ValidationError(
                    f"service exceeds maximum length of {policy.max_service_length}"
                )
            if not all(c.isalnum() or c in "-_" for c in value):
                raise ValidationError("service contains invalid characters")
            cleaned["service"] = value

        if "limit" in inputs:
            try:
                value = int(inputs["limit"])
            except (TypeError, ValueError):
                raise ValidationError("limit must be an integer")
            if value < 1:
                raise ValidationError("limit must be at least 1")
            if value > policy.max_result_limit:
                value = policy.max_result_limit
            cleaned["limit"] = value

        if "minutes" in inputs:
            try:
                value = int(inputs["minutes"])
            except (TypeError, ValueError):
                raise ValidationError("minutes must be an integer")
            if policy.min_minutes is not None and value < policy.min_minutes:
                raise ValidationError(f"minutes must be at least {policy.min_minutes}")
            if policy.max_minutes is not None and value > policy.max_minutes:
                raise ValidationError(f"minutes must be at most {policy.max_minutes}")
            cleaned["minutes"] = value

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

    policy = engine.authorize_tool(tool_name, agent_clean)

    engine.check_rate_limit(tool_name, tenant_clean, policy)

    validated_inputs = engine.validate_inputs(tool_name, policy, dict(inputs or {}))

    return agent_clean, tenant_clean, policy, validated_inputs
