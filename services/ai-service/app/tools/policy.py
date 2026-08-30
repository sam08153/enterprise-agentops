"""
Tool policy / safety boundary.

All agent tool calls pass through authorize_tool() before execution.
READ_ONLY_TOOLS are always permitted.
Any tool not in this set is blocked and requires explicit approval.
"""

READ_ONLY_TOOLS: set[str] = {
    "get_incident",
    "get_logs",
    "get_metrics",
    "get_recent_deployment",
}


def authorize_tool(tool_name: str) -> bool:
    """
    Authorize a tool call.

    Returns True if the tool is permitted to execute.
    Returns False if the tool is not in the allowed set (blocked).

    Architecture note:
      Tool → Policy Engine → Allowed? → YES: Execute / NO: Block
    """
    return tool_name in READ_ONLY_TOOLS
