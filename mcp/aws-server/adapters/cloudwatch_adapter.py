from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


MOCK_LOG_SEEDS: Dict[str, List[Dict[str, Any]]] = {
    "payment-service": [
        {
            "timestamp": "2026-08-30T14:28:30",
            "level": "INFO",
            "message": "Starting application v2.4.1 on instance i-0abc123",
            "stream": "payment-service/i-0abc123",
        },
        {
            "timestamp": "2026-08-30T14:31:02",
            "level": "WARN",
            "message": "Request latency elevated: p95=780ms",
            "stream": "payment-service/i-0abc123",
        },
        {
            "timestamp": "2026-08-30T14:32:15",
            "level": "ERROR",
            "message": "PaymentTimeoutException: Stripe gateway did not respond within 3000ms (attempt 1/3)",
            "stream": "payment-service/i-0def456",
        },
        {
            "timestamp": "2026-08-30T14:32:48",
            "level": "ERROR",
            "message": "PaymentTimeoutException: Stripe gateway did not respond within 3000ms (attempt 2/3)",
            "stream": "payment-service/i-0def456",
        },
        {
            "timestamp": "2026-08-30T14:33:10",
            "level": "ERROR",
            "message": "HTTP 500 sent to client | request_id=req-20260830-001 | cause=PaymentTimeoutException",
            "stream": "payment-service/i-0def456",
        },
        {
            "timestamp": "2026-08-30T14:33:40",
            "level": "ERROR",
            "message": "PaymentTimeoutException on checkout flow (order_id=ord-9876)",
            "stream": "payment-service/i-0abc123",
        },
        {
            "timestamp": "2026-08-30T14:34:20",
            "level": "WARN",
            "message": "Circuit breaker state: HALF_OPEN for stripe-primary",
            "stream": "payment-service/i-0abc123",
        },
        {
            "timestamp": "2026-08-30T14:36:05",
            "level": "ERROR",
            "message": "PaymentTimeoutException - gateway connection pool exhausted (48/50 held)",
            "stream": "payment-service/i-0ghi789",
        },
    ],
    "auth-service": [
        {
            "timestamp": "2026-08-30T10:10:00",
            "level": "INFO",
            "message": "Auth service healthy, 12M tokens minted today",
            "stream": "auth-service/i-0auth001",
        }
    ],
    "order-service": [
        {
            "timestamp": "2026-08-30T14:25:00",
            "level": "INFO",
            "message": "Order creation throughput: 82/s",
            "stream": "order-service/i-0ord001",
        }
    ],
}


class CloudWatchAdapter:
    """
    Adapter layer for CloudWatch Logs.

    Architecture boundary: MCP tools NEVER call boto3 directly.
    They call the service, which calls this adapter.

    Production: replace the mock implementation with boto3 calls
    pointing to a real AWS account (with least-privilege IAM role)
    or LocalStack endpoint (development).
    """

    def __init__(self, use_mock: Optional[bool] = None) -> None:
        if use_mock is None:
            use_mock = os.environ.get("AWS_MCP_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self._use_mock = use_mock
        self._mock_latency_ms = int(os.environ.get("AWS_MCP_MOCK_LATENCY_MS", "30"))
        self._boto3_client = None
        self._region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
        if not self._use_mock:
            try:
                import boto3  # type: ignore
                endpoint = os.environ.get("AWS_ENDPOINT_URL")
                self._boto3_client = boto3.client(
                    "logs",
                    region_name=self._region,
                    endpoint_url=endpoint,
                )
            except Exception as e:
                logger.warning("boto3 CloudWatch Logs client unavailable (%s). Falling back to mock.", e)
                self._use_mock = True

    def _sleep_latency(self) -> None:
        if self._mock_latency_ms > 0:
            time.sleep(self._mock_latency_ms / 1000.0)

    def get_log_events(
        self,
        service: str,
        minutes: int,
        max_items: int = 200,
    ) -> List[Dict[str, Any]]:
        self._sleep_latency()
        if self._use_mock or self._boto3_client is None:
            return self._mock_get_log_events(service, minutes, max_items)
        return self._boto3_get_log_events(service, minutes, max_items)

    def _mock_get_log_events(
        self, service: str, minutes: int, max_items: int
    ) -> List[Dict[str, Any]]:
        raw = list(MOCK_LOG_SEEDS.get(service, []))
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=minutes)
        filtered: List[Dict[str, Any]] = []
        for entry in raw:
            try:
                ts = datetime.fromisoformat(entry["timestamp"]).replace(tzinfo=timezone.utc)
            except Exception:
                ts = now
            if ts >= cutoff or minutes >= 24 * 60:
                filtered.append(dict(entry))
        return filtered[:max_items]

    def _boto3_get_log_events(
        self, service: str, minutes: int, max_items: int
    ) -> List[Dict[str, Any]]:
        assert self._boto3_client is not None
        import boto3  # noqa: F401
        log_group = os.environ.get("CLOUDWATCH_LOG_GROUP_PATTERN", "/ecs/{service}").format(service=service)
        start = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
        end = int(datetime.now(timezone.utc).timestamp() * 1000)
        try:
            resp = self._boto3_client.filter_log_events(
                logGroupName=log_group,
                startTime=start,
                endTime=end,
                limit=max_items,
            )
            out: List[Dict[str, Any]] = []
            for evt in resp.get("events", []):
                out.append(
                    {
                        "timestamp": datetime.fromtimestamp(
                            (evt.get("timestamp") or 0) / 1000.0, tz=timezone.utc
                        ).isoformat(),
                        "level": self._infer_level(evt.get("message", "")),
                        "message": str(evt.get("message", "")),
                        "stream": str(evt.get("logStreamName", "")),
                    }
                )
            return out
        except Exception as e:
            logger.error("CloudWatch query failed: %s", e)
            raise

    @staticmethod
    def _infer_level(message: str) -> str:
        m = (message or "").upper()
        for lvl in ("ERROR", "WARN", "WARNING", "INFO", "DEBUG", "TRACE", "FATAL"):
            if lvl in m:
                return "WARN" if lvl == "WARNING" else lvl
        return "INFO"
