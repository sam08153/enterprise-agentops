from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


MOCK_METRICS: Dict[str, Dict[str, Any]] = {
    "payment-service": {
        "error_rate": 18.2,
        "error_rate_previous": 1.2,
        "latency_p95_ms": 920,
        "latency_p95_previous": 240,
        "latency_p50_ms": 180,
        "request_count": 18432,
        "request_rate_per_sec": 412,
        "cpu_percent": 54,
        "memory_percent": 61,
        "db_pool_active": 48,
        "db_pool_max": 50,
    },
    "auth-service": {
        "error_rate": 0.4,
        "error_rate_previous": 0.3,
        "latency_p95_ms": 120,
        "latency_p95_previous": 115,
        "latency_p50_ms": 22,
        "request_count": 245000,
        "request_rate_per_sec": 5400,
        "cpu_percent": 32,
        "memory_percent": 48,
        "db_pool_active": 12,
        "db_pool_max": 80,
    },
    "order-service": {
        "error_rate": 2.1,
        "error_rate_previous": 1.8,
        "latency_p95_ms": 310,
        "latency_p95_previous": 280,
        "latency_p50_ms": 60,
        "request_count": 72500,
        "request_rate_per_sec": 1600,
        "cpu_percent": 41,
        "memory_percent": 55,
        "db_pool_active": 22,
        "db_pool_max": 100,
    },
}


class MetricsAdapter:
    """Adapter for CloudWatch Metrics (GetMetricData / GetMetricStatistics)."""

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        if use_mock is None:
            use_mock = os.environ.get("AWS_MCP_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self._use_mock = use_mock
        self._mock_latency_ms = int(os.environ.get("AWS_MCP_MOCK_LATENCY_MS", "25"))
        self._cw_client = None
        self._region = os.environ.get("AWS_REGION", "us-east-1")
        if not self._use_mock:
            try:
                import boto3  # type: ignore
                self._cw_client = boto3.client(
                    "cloudwatch",
                    region_name=self._region,
                    endpoint_url=os.environ.get("AWS_ENDPOINT_URL"),
                )
            except Exception as e:
                logger.warning("boto3 CloudWatch Metrics unavailable (%s). Mock fallback.", e)
                self._use_mock = True

    def _sleep(self) -> None:
        if self._mock_latency_ms > 0:
            time.sleep(self._mock_latency_ms / 1000.0)

    def get_service_metrics(self, service: str, window_minutes: int) -> Dict[str, Any]:
        self._sleep()
        if self._use_mock or self._cw_client is None:
            base = dict(MOCK_METRICS.get(service, MOCK_METRICS["payment-service"]))
            base["service"] = service
            base["window_minutes"] = window_minutes
            base["region"] = self._region
            base["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            return base
        return self._boto3_get(service, window_minutes)

    def _boto3_get(self, service: str, window_minutes: int) -> Dict[str, Any]:
        assert self._cw_client is not None
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=window_minutes)
        ns = os.environ.get("CLOUDWATCH_METRIC_NAMESPACE", "AWSOps/EnterpriseAgentOps")
        queries = [
            {"Id": "error_rate", "MetricStat": {"Metric": {"Namespace": ns, "MetricName": f"{service}/error_rate", "Dimensions": []}, "Period": 60, "Stat": "Average"}},
            {"Id": "latency_p95", "MetricStat": {"Metric": {"Namespace": ns, "MetricName": f"{service}/latency_p95", "Dimensions": []}, "Period": 60, "Stat": "p95"}},
            {"Id": "req_count", "MetricStat": {"Metric": {"Namespace": ns, "MetricName": f"{service}/request_count", "Dimensions": []}, "Period": 60, "Stat": "Sum"}},
            {"Id": "cpu", "MetricStat": {"Metric": {"Namespace": "CWAgent", "MetricName": "cpu_usage_percent", "Dimensions": [{"Name": "Service", "Value": service}]}, "Period": 60, "Stat": "Average"}},
        ]
        try:
            resp = self._cw_client.get_metric_data(
                MetricDataQueries=queries,
                StartTime=start,
                EndTime=end,
            )
            out: Dict[str, Any] = {"service": service, "window_minutes": window_minutes, "region": self._region}
            for r in resp.get("MetricDataResults", []):
                vals = r.get("Values") or []
                out[r["Id"]] = float(vals[-1]) if vals else 0.0
            return out
        except Exception as e:
            logger.error("CloudWatch metrics query failed: %s", e)
            raise


MOCK_DEPLOYMENTS: Dict[str, Dict[str, Any]] = {
    "payment-service": {
        "service": "payment-service",
        "version": "v2.4.1",
        "deployed_at": "2026-08-30T14:28:00",
        "deployed_by": "jenkins+ci-bot",
        "previous_version": "v2.4.0",
        "commit_sha": "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4",
        "environment": "production",
        "status": "SUCCEEDED",
    },
    "auth-service": {
        "service": "auth-service",
        "version": "v1.8.0",
        "deployed_at": "2026-08-28T09:15:00",
        "deployed_by": "deploy-bot",
        "previous_version": "v1.7.9",
        "commit_sha": "deadbeefcafebabe0011223344556677889900aa",
        "environment": "production",
        "status": "SUCCEEDED",
    },
    "order-service": {
        "service": "order-service",
        "version": "v3.1.2",
        "deployed_at": "2026-08-29T22:04:00",
        "deployed_by": "deploy-bot",
        "previous_version": "v3.1.1",
        "commit_sha": "cafebabedeadbeef00112233445566778899aabb",
        "environment": "production",
        "status": "SUCCEEDED",
    },
}


class DeploymentAdapter:
    """Adapter for reading deployment metadata from ECS / CodeDeploy / local mock."""

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        if use_mock is None:
            use_mock = os.environ.get("AWS_MCP_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self._use_mock = use_mock
        self._mock_latency_ms = int(os.environ.get("AWS_MCP_MOCK_LATENCY_MS", "15"))
        self._ecs_client = None
        self._codedeploy_client = None
        if not self._use_mock:
            try:
                import boto3  # type: ignore
                region = os.environ.get("AWS_REGION", "us-east-1")
                endpoint = os.environ.get("AWS_ENDPOINT_URL")
                self._ecs_client = boto3.client("ecs", region_name=region, endpoint_url=endpoint)
                self._codedeploy_client = boto3.client("codedeploy", region_name=region, endpoint_url=endpoint)
            except Exception as e:
                logger.warning("boto3 deployment clients unavailable (%s). Mock fallback.", e)
                self._use_mock = True

    def get_recent_deployment(self, service: str) -> Optional[Dict[str, Any]]:
        if self._mock_latency_ms > 0:
            time.sleep(self._mock_latency_ms / 1000.0)
        if self._use_mock:
            return dict(MOCK_DEPLOYMENTS.get(service, MOCK_DEPLOYMENTS["payment-service"]))
        return self._boto3_get(service)

    def _boto3_get(self, service: str) -> Optional[Dict[str, Any]]:
        try:
            if self._codedeploy_client:
                app = os.environ.get("CODEDEPLOY_APP_PATTERN", "{service}-app").format(service=service)
                dg = os.environ.get("CODEDEPLOY_DG_PATTERN", "{service}-dg").format(service=service)
                resp = self._codedeploy_client.list_deployments(
                    applicationName=app,
                    deploymentGroupName=dg,
                    includeOnlyStatuses=["Succeeded", "Failed", "InProgress"],
                )
                ids = resp.get("deployments", [])
                if ids:
                    detail = self._codedeploy_client.get_deployment(deploymentId=ids[0])["deploymentInfo"]
                    return {
                        "service": service,
                        "version": detail.get("revision", {}).get("revisionId", "unknown"),
                        "deployed_at": str(detail.get("createTime", "")),
                        "previous_version": "",
                        "deployed_by": str(detail.get("creator", "")),
                        "environment": "production",
                        "status": str(detail.get("status", "")),
                    }
        except Exception as e:
            logger.error("CodeDeploy query failed: %s", e)
            raise
        return None


MOCK_HEALTH: Dict[str, Dict[str, Any]] = {
    "payment-service": {
        "service": "payment-service",
        "status": "DEGRADED",
        "healthy_instances": 8,
        "unhealthy_instances": 2,
        "desired_instances": 10,
        "last_checked_at": "",
    },
    "auth-service": {
        "service": "auth-service",
        "status": "HEALTHY",
        "healthy_instances": 6,
        "unhealthy_instances": 0,
        "desired_instances": 6,
        "last_checked_at": "",
    },
    "order-service": {
        "service": "order-service",
        "status": "HEALTHY",
        "healthy_instances": 8,
        "unhealthy_instances": 0,
        "desired_instances": 8,
        "last_checked_at": "",
    },
}


class HealthAdapter:
    """Adapter for ECS/Kubernetes service health + ASG instance counts."""

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        if use_mock is None:
            use_mock = os.environ.get("AWS_MCP_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self._use_mock = use_mock
        self._mock_latency_ms = int(os.environ.get("AWS_MCP_MOCK_LATENCY_MS", "10"))
        self._ecs_client = None
        if not self._use_mock:
            try:
                import boto3  # type: ignore
                region = os.environ.get("AWS_REGION", "us-east-1")
                self._ecs_client = boto3.client("ecs", region_name=region, endpoint_url=os.environ.get("AWS_ENDPOINT_URL"))
            except Exception as e:
                logger.warning("boto3 ECS client unavailable (%s). Mock fallback.", e)
                self._use_mock = True

    def get_service_health(self, service: str) -> Dict[str, Any]:
        if self._mock_latency_ms > 0:
            time.sleep(self._mock_latency_ms / 1000.0)
        if self._use_mock or self._ecs_client is None:
            base = dict(MOCK_HEALTH.get(service, MOCK_HEALTH["payment-service"]))
            base["last_checked_at"] = datetime.now(timezone.utc).isoformat()
            return base
        return self._boto3_get(service)

    def _boto3_get(self, service: str) -> Dict[str, Any]:
        assert self._ecs_client is not None
        cluster = os.environ.get("ECS_CLUSTER", "production")
        svc = f"{service}-svc"
        try:
            resp = self._ecs_client.describe_services(cluster=cluster, services=[svc])
            s = (resp.get("services") or [{}])[0]
            running = int(s.get("runningCount", 0))
            desired = int(s.get("desiredCount", 0))
            pending = int(s.get("pendingCount", 0))
            status = "HEALTHY" if pending == 0 and running == desired else "DEGRADED"
            if running < max(1, desired - 2):
                status = "UNHEALTHY"
            return {
                "service": service,
                "status": status,
                "healthy_instances": running,
                "unhealthy_instances": max(0, desired - running),
                "desired_instances": desired,
                "last_checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error("ECS describe_services failed: %s", e)
            raise
