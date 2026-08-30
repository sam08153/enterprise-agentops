def get_incident(incident_id: str) -> dict:
    """Get incident information by ID. Returns current status, severity, and description."""
    return {
        "incident_id": incident_id,
        "service": "payment-service",
        "severity": "HIGH",
        "error_rate": "18%",
        "started_at": "2026-08-30T14:32:00",
        "description": "HTTP 500 errors increased significantly after recent deployment",
    }


# Tool definition for the LLM
INCIDENT_TOOL_DEFINITION = {
    "name": "get_incident",
    "description": "Retrieve incident details including severity, error rate, affected service, and timeline.",
    "input_schema": {
        "type": "object",
        "properties": {
            "incident_id": {
                "type": "string",
                "description": "The unique incident identifier, e.g. INC-1001",
            }
        },
        "required": ["incident_id"],
    },
}
