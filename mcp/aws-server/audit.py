from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    tool_name: str
    agent_name: str
    tenant_id: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    status: str
    duration_ms: int
    source: str = "aws-mcp"
    started_at: float = 0.0

    @property
    def as_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "agent_name": self.agent_name,
            "tenant_id": self.tenant_id,
            "source": self.source,
            "input": self.input_data,
            "output": self.output_data,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at or time.time(),
        }


class AuditLogger:
    def __init__(self, write_to_stdout: Optional[bool] = None) -> None:
        import os
        self._write_stdout = (
            write_to_stdout
            if write_to_stdout is not None
            else os.environ.get("AWS_MCP_AUDIT_STDOUT", "true").lower() in ("1", "true", "yes")
        )

    def record(self, rec: AuditRecord) -> None:
        if self._write_stdout:
            logger.info(
                "AUDIT aws_mcp tool=%s agent=%s tenant=%s status=%s duration_ms=%s",
                rec.tool_name,
                rec.agent_name,
                rec.tenant_id,
                rec.status,
                rec.duration_ms,
            )
        try:
            self._write_to_db(rec)
        except Exception as e:
            logger.warning("DB audit write failed (non-fatal): %s", e)

    def _write_to_db(self, rec: AuditRecord) -> None:
        try:
            sys_path_saved = list(sys.path)
            try:
                import os
                import sys
                pg_dir = os.path.normpath(
                    os.path.join(os.path.dirname(__file__), "..", "postgres-server")
                )
                if pg_dir not in sys.path:
                    sys.path.insert(0, pg_dir)
                from database import get_db as _pg_db
                pg_db = _pg_db()
                pg_db.audit_tool_execution(
                    tool_name=f"aws.{rec.tool_name}",
                    agent_name=rec.agent_name,
                    tenant_id=rec.tenant_id,
                    input_data=rec.input_data,
                    output_data=rec.output_data,
                    status=rec.status,
                    duration_ms=max(1, rec.duration_ms),
                )
            finally:
                sys.path[:] = sys_path_saved
        except Exception:
            pass


_audit = AuditLogger()


def audit_logger() -> AuditLogger:
    return _audit
