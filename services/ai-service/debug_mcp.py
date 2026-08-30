import io
import os
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MCP_USE_LOCAL", "true")
os.environ.setdefault("MCP_USE_MOCK", "true")
os.environ.setdefault("MOCK_MODE", "true")

print("--- Debug AWS MCP client ---")
from app.tools.logs import get_logs
result = get_logs("payment-service", minutes=60)
print("get_logs result keys:", list(result.keys())[:8])
print("error:", result.get("error"))
print("error_type:", result.get("error_type"))
print()

from app.tools.metrics import get_metrics
r = get_metrics("payment-service")
print("get_metrics error:", r.get("error"), r.get("error_type"))
print("metrics keys:", list(r.get("metrics", {}).keys())[:6] if r.get("metrics") else None)
print()

from app.tools.github import get_recent_commits, search_code
r = get_recent_commits("payments")
print("get_recent_commits error:", r.get("error"), r.get("error_type"))
print("total_returned:", r.get("total_returned"))
print()

r = search_code("payments", "timeout")
print("search_code error:", r.get("error"), r.get("error_type"))
print("total_returned:", r.get("total_returned"))
