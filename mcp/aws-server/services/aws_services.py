from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from adapters.aws_adapters import (
    DeploymentAdapter,
    HealthAdapter,
    MetricsAdapter,
)
from adapters.cloudwatch_adapter import CloudWatchAdapter

logger = logging.getLogger(__name__)


class CloudWatchService:
    """
    High-level service for CloudWatch logs.

    Responsibility: shape the adapter output into the domain representation
    consumed by MCP tools (chronological ordering, level normalization,
    size caps, structured summary counts). Agents should call this service
    rather than the adapter directly.
    """

    def __init__(self, adapter: Optional[CloudWatchAdapter] = None) -> None:
        self._adapter = adapter or CloudWatchAdapter()

    def get_logs(
        self,
        service: str,
        minutes: int,
        max_items: int = 200,
    ) -> Dict[str, Any]:
        raw = self._adapter.get_log_events(service=service, minutes=minutes, max_items=max_items)
        raw.sort(key=lambda r: r.get("timestamp", ""))
        counts: Dict[str, int] = {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0, "FATAL": 0, "TRACE": 0, "OTHER": 0}
        for entry in raw:
            lvl = str(entry.get("level", "OTHER")).upper()
            if lvl in counts:
                counts[lvl] += 1
            else:
                counts["OTHER"] += 1
        return {
            "service": service,
            "window_minutes": minutes,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "total_returned": len(raw),
            "log_level_counts": counts,
            "logs": raw,
        }


class MetricsService:
    """High-level service that returns structured operational metrics."""

    def __init__(self, adapter: Optional[MetricsAdapter] = None) -> None:
        self._adapter = adapter or MetricsAdapter()

    def get_metrics(self, service: str, window_minutes: int) -> Dict[str, Any]:
        raw = self._adapter.get_service_metrics(service=service, window_minutes=window_minutes)
        metrics_block = {
            "error_rate": raw.get("error_rate", 0.0),
            "error_rate_delta_vs_previous": round(
                float(raw.get("error_rate", 0.0) or 0.0) - float(raw.get("error_rate_previous", 0.0) or 0.0),
                2,
            ),
            "latency_p95_ms": raw.get("latency_p95_ms", 0),
            "latency_p95_delta_vs_previous": round(
                float(raw.get("latency_p95_ms", 0) or 0) - float(raw.get("latency_p95_previous", 0) or 0),
                1,
            ),
            "latency_p50_ms": raw.get("latency_p50_ms", 0),
            "request_count": raw.get("request_count", 0),
            "request_rate_per_sec": raw.get("request_rate_per_sec", 0),
            "cpu_percent": raw.get("cpu_percent", 0),
            "memory_percent": raw.get("memory_percent", 0),
            "db_pool_active": raw.get("db_pool_active"),
            "db_pool_max": raw.get("db_pool_max"),
        }
        return {
            "service": raw.get("service", service),
            "window_minutes": window_minutes,
            "retrieved_at": raw.get("retrieved_at") or datetime.now(timezone.utc).isoformat(),
            "region": raw.get("region"),
            "metrics": metrics_block,
        }


class DeploymentService:
    """High-level service for most-recent deployment lookup."""

    def __init__(self, adapter: Optional[DeploymentAdapter] = None) -> None:
        self._adapter = adapter or DeploymentAdapter()

    def get_recent(self, service: str) -> Dict[str, Any]:
        record = self._adapter.get_recent_deployment(service) or {}
        return {
            "service": service,
            "version": record.get("version", "unknown"),
            "deployed_at": record.get("deployed_at", ""),
            "previous_version": record.get("previous_version", ""),
            "deployed_by": record.get("deployed_by", ""),
            "commit_sha": record.get("commit_sha", ""),
            "environment": record.get("environment", "production"),
            "status": record.get("status", "UNKNOWN"),
        }


class HealthService:
    def __init__(self, adapter: Optional[HealthAdapter] = None) -> None:
        self._adapter = adapter or HealthAdapter()

    def get_health(self, service: str) -> Dict[str, Any]:
        raw = self._adapter.get_service_health(service)
        status = raw.get("status", "UNKNOWN")
        healthy = int(raw.get("healthy_instances", 0) or 0)
        unhealthy = int(raw.get("unhealthy_instances", 0) or 0)
        desired = int(raw.get("desired_instances", 0) or 0)
        return {
            "service": service,
            "status": status,
            "healthy_instances": healthy,
            "unhealthy_instances": unhealthy,
            "desired_instances": desired,
            "health_percent": round(100.0 * healthy / max(1, desired), 1),
            "last_checked_at": raw.get("last_checked_at") or datetime.now(timezone.utc).isoformat(),
        }


_cloudwatch = CloudWatchService()
_metrics = MetricsService()
_deployments = DeploymentService()
_health = HealthService()


def cloudwatch_service() -> CloudWatchService:
    return _cloudwatch


def metrics_service() -> MetricsService:
    return _metrics


def deployment_service() -> DeploymentService:
    return _deployments


def health_service() -> HealthService:
    return _health
