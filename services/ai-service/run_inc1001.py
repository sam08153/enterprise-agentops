import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("MCP_USE_LOCAL", "true")
os.environ.setdefault("MCP_USE_MOCK", "true")
os.environ.setdefault("MOCK_MODE", "true")

from app.agent.graph import run_investigation_graph

print("=" * 80)
print("INC-1001 End-to-End RCA Investigation")
print("=" * 80)

result = run_investigation_graph(
    incident_id="INC-1001",
    tenant_id="demo",
    thread_id="incident-INC-1001-e2e",
    max_iterations=2,
    max_tool_calls=20,
)

print()
print("Incident:   ", result.incident_id)
print("Service:    ", result.service)
print("Tool calls: ", result.tool_calls)
print("Tokens:     ", f"in={result.input_tokens} out={result.output_tokens}")
print("Confidence: ", result.confidence)
print()
print("--- SUMMARY ---")
print(result.summary)
print()
print("--- ROOT CAUSE ---")
print(result.root_cause)
print()
print("--- EVIDENCE (" + str(len(result.evidence)) + " items) ---")
for i, e in enumerate(result.evidence, 1):
    print(f"  {i}. {e}")
print()
print("--- RECOMMENDED ACTIONS ---")
for i, a in enumerate(result.recommended_actions, 1):
    print(f"  {i}. {a}")
print()
print("--- ACTIONS EXECUTED ---")
print("  NO (agent recommendations only; human approval required)")
print()

if result.tool_executions:
    print("--- TOOL EXECUTION AUDIT (" + str(len(result.tool_executions)) + ") ---")
    for te in result.tool_executions:
        try:
            out_sz = len(te.output) if te.output else 0
            status_clr = te.status
            name = te.tool_name
            dur = te.duration_ms
            print(f"  {name:<32s} status={status_clr:<12s} dur_ms={dur:<5d} out_bytes={out_sz}")
        except Exception:
            print(repr(te))

print()
print("=" * 80)
if result.confidence >= 0.85 and "v2.4.1" in result.root_cause and "timeout" in result.root_cause.lower():
    print("PASS: Root cause correctly identified v2.4.1 timeout regression.")
else:
    print(f"REVIEW: confidence={result.confidence}; root_cause includes v2.4.1+timeout?")
print("=" * 80)
