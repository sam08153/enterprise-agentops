"""
Agent runtime using Groq (Qwen 3) — free tier, supports tool calling.
"""

import json
import logging
from datetime import datetime, timezone

from app.agent.prompts import INVESTIGATION_SYSTEM_PROMPT
from app.models.incident import RCAResponse, ToolExecutionRecord
from app.tools.incident import get_incident, INCIDENT_TOOL_DEFINITION
from app.tools.logs import get_logs, LOGS_TOOL_DEFINITION
from app.tools.deployment import get_recent_deployment, DEPLOYMENT_TOOL_DEFINITION
from app.tools.metrics import get_metrics, METRICS_TOOL_DEFINITION
from app.tools.policy import authorize_tool

logger = logging.getLogger(__name__)

GROQ_MODEL = "qwen/qwen3.8-27b"

# Registry: maps tool name → callable
TOOL_REGISTRY: dict = {
    "get_incident": get_incident,
    "get_logs": get_logs,
    "get_recent_deployment": get_recent_deployment,
    "get_metrics": get_metrics,
}

# Tool definitions in OpenAI function-calling format (Groq-compatible)
TOOL_DEFINITIONS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": d["name"],
            "description": d["description"],
            "parameters": d["input_schema"],
        },
    }
    for d in [
        INCIDENT_TOOL_DEFINITION,
        LOGS_TOOL_DEFINITION,
        DEPLOYMENT_TOOL_DEFINITION,
        METRICS_TOOL_DEFINITION,
    ]
]


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Policy-gated tool executor."""
    if not authorize_tool(tool_name):
        logger.warning("Tool '%s' blocked by policy.", tool_name)
        return {"error": f"Tool '{tool_name}' is not permitted by security policy."}

    fn = TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return {"error": f"Tool '{tool_name}' is not registered."}

    logger.info("Executing tool: %s | input: %s", tool_name, tool_input)
    result = fn(**tool_input)
    logger.info("Tool result for %s: %s", tool_name, result)
    return result


def extract_json(text: str) -> dict:
    """
    Robust JSON extractor that finds and parses JSON blocks or raw structures
    nested inside LLM conversational text.
    """
    text = text.strip()

    # 1. Try to extract JSON from ```json ... ``` blocks
    if "```json" in text:
        try:
            return json.loads(text.split("```json")[1].split("```")[0].strip())
        except Exception:
            pass

    # 2. Try to extract JSON from generic ``` ... ``` blocks
    if "```" in text:
        try:
            parts = text.split("```")
            for part in parts[1::2]:
                try:
                    return json.loads(part.strip())
                except Exception:
                    pass
        except Exception:
            pass

    # 3. Locate first '{' and last '}'
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        try:
            return json.loads(text[first_brace:last_brace + 1].strip())
        except Exception:
            pass

    # 4. Direct load
    return json.loads(text)


def run_investigation(incident_id: str, groq_client) -> RCAResponse:
    """
    Core agent loop using Groq's OpenAI-compatible API.
    """
    messages = [
        {"role": "system", "content": INVESTIGATION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Investigate incident {incident_id}. "
                "Use all available tools to gather evidence before providing the RCA."
            ),
        },
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    tool_calls_count = 0
    tool_executions = []

    # --- Agent loop ---
    while True:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            max_tokens=4096,
        )

        # Track usage
        if response.usage:
            total_input_tokens += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens

        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        logger.info("LLM finish_reason: %s", finish_reason)

        # Append assistant message
        messages.append(message)

        if finish_reason == "tool_calls" and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_input = json.loads(tool_call.function.arguments)

                start_time = datetime.now(timezone.utc)
                status = "SUCCESS"
                result = {}
                try:
                    result = execute_tool(tool_name, tool_input)
                    if isinstance(result, dict) and "error" in result:
                        status = "FAILED"
                except Exception as e:
                    status = "FAILED"
                    result = {"error": str(e)}

                end_time = datetime.now(timezone.utc)
                duration = int((end_time - start_time).total_seconds() * 1000)
                tool_calls_count += 1

                tool_executions.append(
                    ToolExecutionRecord(
                        tool_name=tool_name,
                        input=json.dumps(tool_input),
                        output=json.dumps(result),
                        status=status,
                        started_at=start_time.isoformat(),
                        completed_at=end_time.isoformat(),
                        duration_ms=max(1, duration),
                    )
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })

        elif finish_reason == "stop":
            final_text = message.content or ""

            try:
                rca_data = extract_json(final_text)

                # Populate observability fields
                rca = RCAResponse(**rca_data)
                rca.input_tokens = total_input_tokens
                rca.output_tokens = total_output_tokens
                rca.tool_calls = tool_calls_count
                rca.tool_executions = tool_executions
                return rca
            except Exception as e:
                logger.error("Failed to parse RCA JSON: %s\nRaw: %s", e, final_text)
                return RCAResponse(
                    incident_id=incident_id,
                    service="unknown",
                    summary="Agent completed but response could not be parsed as JSON.",
                    root_cause=final_text,
                    confidence=0.0,
                    evidence=[],
                    recommended_actions=["Review agent logs for raw LLM output."],
                    actions_executed=[],
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    tool_calls=tool_calls_count,
                    tool_executions=tool_executions,
                )
        else:
            logger.error("Unexpected finish_reason: %s", finish_reason)
            break
