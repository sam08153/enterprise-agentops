from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://agentops:agentops@localhost:5432/agentops"
)

_service_to_incident_ids: Dict[str, List[str]] = {
    "payment-service": ["INC-1001", "INC-0912", "INC-0847", "INC-0799"],
    "auth-service": ["INC-0888", "INC-0820"],
    "order-service": ["INC-0901", "INC-0855"],
}

_mock_incidents: Dict[str, Dict[str, Any]] = {
    "INC-1001": {
        "incident_id": "INC-1001",
        "tenant_id": "demo",
        "title": "5xx error rate increase from 1% to 18% on payment-service",
        "description": "HTTP 500 errors on checkout flows spiked from baseline ~1% to ~18% starting around 2026-08-30T14:32:00. Multiple PaymentTimeoutException occurrences observed in logs. Deploy v2.4.1 released at 14:28 may be related.",
        "service": "payment-service",
        "severity": "HIGH",
        "status": "ACTIVE",
        "error_rate": "18%",
        "started_at": "2026-08-30T14:32:00",
    },
    "INC-0912": {
        "incident_id": "INC-0912",
        "tenant_id": "demo",
        "title": "Payment timeout regression",
        "description": "HTTP 500 errors increased significantly after recent deployment to payment-service. Users experiencing PaymentTimeoutException on checkout flows.",
        "service": "payment-service",
        "severity": "HIGH",
        "status": "ACTIVE",
        "error_rate": "18%",
        "started_at": "2026-08-30T14:32:00",
    },
    "INC-0847": {
        "incident_id": "INC-0847",
        "tenant_id": "demo",
        "title": "Stripe gateway connection failures",
        "description": "Intermittent connection timeouts to external Stripe payment gateway causing failed charges.",
        "service": "payment-service",
        "severity": "MEDIUM",
        "status": "RESOLVED",
        "error_rate": "8%",
        "started_at": "2026-08-15T09:12:00",
    },
    "INC-0799": {
        "incident_id": "INC-0799",
        "tenant_id": "demo",
        "title": "Database connection pool exhaustion",
        "description": "Payment service database pool hit max connections during peak traffic, causing queued transactions to timeout.",
        "service": "payment-service",
        "severity": "HIGH",
        "status": "RESOLVED",
        "error_rate": "22%",
        "started_at": "2026-07-28T18:45:00",
    },
    "INC-0888": {
        "incident_id": "INC-0888",
        "tenant_id": "demo",
        "title": "JWT token validation errors",
        "description": "Auth service returning 401 for valid tokens due to clock skew between services.",
        "service": "auth-service",
        "severity": "MEDIUM",
        "status": "RESOLVED",
        "error_rate": "12%",
        "started_at": "2026-08-22T11:20:00",
    },
    "INC-0820": {
        "incident_id": "INC-0820",
        "tenant_id": "demo",
        "title": "Slow login response times",
        "description": "Auth service login endpoint latency degraded during morning peak hours.",
        "service": "auth-service",
        "severity": "LOW",
        "status": "RESOLVED",
        "error_rate": "3%",
        "started_at": "2026-08-10T07:30:00",
    },
    "INC-0901": {
        "incident_id": "INC-0901",
        "tenant_id": "demo",
        "title": "Order creation duplicate submissions",
        "description": "Order service allowing duplicate order creation due to missing idempotency key validation.",
        "service": "order-service",
        "severity": "MEDIUM",
        "status": "RESOLVED",
        "error_rate": "5%",
        "started_at": "2026-08-26T15:50:00",
    },
    "INC-0855": {
        "incident_id": "INC-0855",
        "tenant_id": "demo",
        "title": "Inventory sync mismatch",
        "description": "Order service inventory counts out of sync with warehouse system leading to oversells.",
        "service": "order-service",
        "severity": "HIGH",
        "status": "RESOLVED",
        "error_rate": "9%",
        "started_at": "2026-08-18T10:05:00",
    },
}

_mock_documents: Dict[str, Dict[str, Any]] = {
    "DOC-001": {
        "document_id": "DOC-001",
        "tenant_id": "demo",
        "title": "Payment Service Runbook",
        "source": "runbooks/payment-service",
        "content": (
            "# Payment Service Runbook\n\n"
            "## Symptoms\n\n"
            "Common symptoms include:\n\n"
            "- HTTP 500 errors\n"
            "- PaymentTimeoutException\n"
            "- Increased response latency\n"
            "- Failed authorization requests\n\n"
            "## Initial Investigation\n\n"
            "1. Check application logs.\n"
            "2. Check recent deployments.\n"
            "3. Check database latency.\n"
            "4. Check external payment gateway health.\n\n"
            "## Deployment Related Issues\n\n"
            "If the issue started immediately after a deployment:\n\n"
            "1. Compare the current release with the previous release.\n"
            "2. Review recent commits.\n"
            "3. Check timeout configuration.\n"
            "4. Consider rollback if the regression is confirmed.\n\n"
            "## Rollback\n\n"
            "Production rollback requires human approval.\n"
        ),
        "created_at": "2026-07-01T00:00:00",
    },
    "DOC-002": {
        "document_id": "DOC-002",
        "tenant_id": "demo",
        "title": "Payment Service Architecture",
        "source": "architecture/payment-service",
        "content": (
            "# Payment Service Architecture\n\n"
            "## Overview\n\n"
            "Payment service handles all checkout flows, payment processing, and transaction management.\n\n"
            "## Dependencies\n\n"
            "- PostgreSQL (transactions, audit logs)\n"
            "- Redis (rate limiting, idempotency)\n"
            "- Stripe API (external gateway)\n"
            "- Kafka (order events)\n\n"
            "## Failure Modes\n\n"
            "1. Stripe gateway timeouts → circuit breaker opens → fallback to secondary provider\n"
            "2. DB pool exhaustion → queued transactions → latency spike → timeouts\n"
            "3. Schema migrations not backward compatible → write failures during deploy\n"
            "4. Redis cache stampede → DB overload during cold start\n"
        ),
        "created_at": "2026-07-01T00:00:00",
    },
    "DOC-003": {
        "document_id": "DOC-003",
        "tenant_id": "demo",
        "title": "Postmortem INC-0799: DB Pool Exhaustion",
        "source": "incidents/INC-0799",
        "content": (
            "# Postmortem: INC-0799 Database Connection Pool Exhaustion\n\n"
            "## Summary\n\n"
            "On 2026-07-28, payment service experienced 22% error rate for ~45 minutes during evening peak.\n\n"
            "## Root Cause\n\n"
            "New background reconciliation job held open connections without releasing them back to the pool. "
            "Pool size was set to 50, but the job consumed 48 connections, leaving only 2 for request traffic.\n\n"
            "## Action Items\n\n"
            "1. Separate connection pools for request vs background workloads (DONE)\n"
            "2. Add connection leak detection metrics (DONE)\n"
            "3. Set statement timeout of 30s on all connections (DONE)\n"
            "4. Load test pool behavior during simulated peak traffic (TODO)\n"
        ),
        "created_at": "2026-07-29T00:00:00",
    },
}


class Database:
    _instance: Optional["Database"] = None

    def __init__(self) -> None:
        self._conn_info = DATABASE_URL
        self._use_mock = os.environ.get("MCP_USE_MOCK", "true").lower() in ("1", "true", "yes")
        self._mock_delay = float(os.environ.get("MCP_MOCK_DELAY_MS", "20")) / 1000.0

    @classmethod
    def instance(cls) -> "Database":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @contextmanager
    def connection(self) -> Generator[psycopg.Connection, None, None]:
        if self._use_mock:
            yield None
            return
        conn = psycopg.connect(self._conn_info, row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()

    def _sleep_mock(self) -> None:
        if self._mock_delay > 0:
            time.sleep(self._mock_delay)

    def _ensure_tenant(self, tenant_id: str, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        row_tenant = str(row.get("tenant_id", ""))
        if row_tenant and row_tenant != tenant_id:
            return None
        return row

    def get_incident(self, incident_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        self._sleep_mock()
        if self._use_mock:
            inc = _mock_incidents.get(incident_id)
            if inc is None:
                return None
            if str(inc.get("tenant_id")) != tenant_id:
                return None
            return dict(inc)

        with self.connection() as conn:
            if conn is None:
                return None
            cur = conn.execute(
                """
                SELECT
                    i.id::text AS incident_uuid,
                    i.tenant_id::text AS tenant_id,
                    i.title,
                    i.description,
                    i.status,
                    i.severity,
                    i.created_at AS started_at
                FROM incidents i
                WHERE i.title ILIKE %s
                  AND i.tenant_id = (SELECT id FROM tenants WHERE name = %s)
                LIMIT 1
                """,
                (f"%{incident_id}%", tenant_id),
            )
            row = cur.fetchone()
            row = self._ensure_tenant(tenant_id, dict(row) if row else None)
            if row is None:
                return None
            result = dict(row)
            result["incident_id"] = incident_id
            result["service"] = self._infer_service(result.get("title", "") + " " + result.get("description", ""))
            result.setdefault("error_rate", "0%")
            return result

    def search_incidents(self, query: str, tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self._sleep_mock()
        limit = max(1, min(limit, 20))
        q = (query or "").strip().lower()

        if self._use_mock:
            scored: List[tuple[int, Dict[str, Any]]] = []
            for inc in _mock_incidents.values():
                if str(inc.get("tenant_id")) != tenant_id:
                    continue
                haystack = " ".join(
                    [
                        inc.get("incident_id", ""),
                        inc.get("title", ""),
                        inc.get("description", ""),
                        inc.get("service", ""),
                        inc.get("severity", ""),
                    ]
                ).lower()
                if not q or q in haystack:
                    score = haystack.count(q) if q else 1
                    scored.append((score, dict(inc)))
            scored.sort(key=lambda x: (-x[0], x[1].get("started_at", "")), reverse=True)
            return [s[1] for s in scored[:limit]]

        with self.connection() as conn:
            if conn is None:
                return []
            pattern = f"%{q}%" if q else "%"
            cur = conn.execute(
                """
                SELECT
                    i.id::text AS incident_uuid,
                    i.tenant_id::text AS tenant_id,
                    i.title,
                    i.description,
                    i.status,
                    i.severity,
                    i.created_at AS started_at
                FROM incidents i
                WHERE (i.title ILIKE %s OR i.description ILIKE %s)
                  AND i.tenant_id = (SELECT id FROM tenants WHERE name = %s)
                ORDER BY i.created_at DESC
                LIMIT %s
                """,
                (pattern, pattern, tenant_id, limit),
            )
            rows = cur.fetchall()
            results: List[Dict[str, Any]] = []
            for idx, row in enumerate(rows):
                r = dict(row)
                r["incident_id"] = f"INC-{9000 - idx}"
                r["service"] = self._infer_service(r.get("title", "") + " " + r.get("description", ""))
                r.setdefault("error_rate", "0%")
                results.append(r)
            return results

    def get_incident_history(self, service: str, tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self._sleep_mock()
        limit = max(1, min(limit, 20))
        svc = (service or "").strip().lower()

        if self._use_mock:
            ids = _service_to_incident_ids.get(svc, [])
            results: List[Dict[str, Any]] = []
            for iid in ids:
                inc = _mock_incidents.get(iid)
                if inc and str(inc.get("tenant_id")) == tenant_id:
                    results.append(dict(inc))
            return results[:limit]

        all_incidents = self.search_incidents(svc, tenant_id, limit)
        return [i for i in all_incidents if self._infer_service(i.get("title", "") + " " + i.get("description", "")).lower() == svc][:limit]

    def search_documents(self, query: str, tenant_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        self._sleep_mock()
        limit = max(1, min(limit, 20))
        q = (query or "").strip().lower()

        if self._use_mock:
            scored: List[tuple[int, Dict[str, Any]]] = []
            for doc in _mock_documents.values():
                if str(doc.get("tenant_id")) != tenant_id:
                    continue
                haystack = " ".join(
                    [
                        doc.get("document_id", ""),
                        doc.get("title", ""),
                        doc.get("content", ""),
                        doc.get("source", ""),
                    ]
                ).lower()
                if not q or q in haystack:
                    score = haystack.count(q) if q else 1
                    scored.append((score, dict(doc)))
            scored.sort(key=lambda x: -x[0])
            return [s[1] for s in scored[:limit]]

        with self.connection() as conn:
            if conn is None:
                return []
            pattern = f"%{q}%" if q else "%"
            cur = conn.execute(
                """
                SELECT
                    d.id::text AS document_id,
                    d.tenant_id::text AS tenant_id,
                    d.title,
                    d.content,
                    d.source,
                    d.created_at
                FROM documents d
                WHERE (d.title ILIKE %s OR d.content ILIKE %s)
                  AND d.tenant_id = (SELECT id FROM tenants WHERE name = %s)
                ORDER BY d.created_at DESC
                LIMIT %s
                """,
                (pattern, pattern, tenant_id, limit),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def get_document(self, document_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        self._sleep_mock()
        if self._use_mock:
            doc = _mock_documents.get(document_id)
            if doc is None:
                for d in _mock_documents.values():
                    if d.get("source") == document_id or d.get("title") == document_id:
                        doc = d
                        break
            if doc is None:
                return None
            if str(doc.get("tenant_id")) != tenant_id:
                return None
            return dict(doc)

        with self.connection() as conn:
            if conn is None:
                return None
            cur = conn.execute(
                """
                SELECT
                    d.id::text AS document_id,
                    d.tenant_id::text AS tenant_id,
                    d.title,
                    d.content,
                    d.source,
                    d.created_at
                FROM documents d
                WHERE (d.id::text = %s OR d.source = %s OR d.title = %s)
                  AND d.tenant_id = (SELECT id FROM tenants WHERE name = %s)
                LIMIT 1
                """,
                (document_id, document_id, document_id, tenant_id),
            )
            row = cur.fetchone()
            row = self._ensure_tenant(tenant_id, dict(row) if row else None)
            return row

    def get_runbook_resource(self, service: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        svc = (service or "").strip().lower()
        if svc == "payment-service":
            return self.get_document("DOC-001", tenant_id)
        docs = self.search_documents(f"runbook {service}", tenant_id, limit=5)
        for d in docs:
            if "runbook" in str(d.get("source", "")).lower() or "runbook" in str(d.get("title", "")).lower():
                return d
        return docs[0] if docs else None

    def audit_tool_execution(
        self,
        tool_name: str,
        agent_name: str,
        tenant_id: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        status: str,
        duration_ms: int,
    ) -> None:
        logger.info(
            "tool_execution agent=%s tool=%s tenant=%s status=%s duration_ms=%s",
            agent_name,
            tool_name,
            tenant_id,
            status,
            duration_ms,
        )
        if self._use_mock:
            return
        try:
            import json
            with self.connection() as conn:
                if conn is None:
                    return
                conn.execute(
                    """
                    INSERT INTO tool_executions (tool_name, input, output, status, started_at, completed_at, duration_ms)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s)
                    """,
                    (tool_name, json.dumps(input_data), json.dumps(output_data), status, duration_ms),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Failed to write audit record: %s", e)

    @staticmethod
    def _infer_service(text: str) -> str:
        t = (text or "").lower()
        if "payment" in t or "checkout" in t or "stripe" in t:
            return "payment-service"
        if "auth" in t or "login" in t or "jwt" in t or "token" in t:
            return "auth-service"
        if "order" in t or "inventory" in t or "checkout" in t:
            return "order-service"
        return "unknown"


def get_db() -> Database:
    return Database.instance()
