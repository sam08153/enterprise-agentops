def get_recent_deployment(service: str) -> dict:
    """Retrieve the most recent deployment for a service."""
    return {
        "service": service,
        "version": "v2.4.1",
        "deployed_at": "2026-08-30T14:28:00",
        "deployed_by": "ci-pipeline",
        "previous_version": "v2.4.0",
        "changelog_url": "https://github.com/org/payment-service/compare/v2.4.0...v2.4.1",
    }


DEPLOYMENT_TOOL_DEFINITION = {
    "name": "get_recent_deployment",
    "description": "Get information about the most recent deployment for a service, including version and timing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "The name of the service to retrieve deployment info for",
            }
        },
        "required": ["service"],
    },
}
