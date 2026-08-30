def get_logs(service: str, minutes: int = 30) -> dict:
    """Retrieve application logs for a service over a given lookback window."""
    return {
        "service": service,
        "minutes": minutes,
        "logs": [
            "14:31:52 ERROR PaymentTimeoutException: upstream connection timed out",
            "14:32:01 ERROR PaymentTimeoutException: upstream connection timed out",
            "14:32:04 ERROR PaymentTimeoutException: upstream connection timed out",
            "14:32:10 ERROR Database connection timeout after 5000ms",
            "14:32:14 ERROR PaymentTimeoutException: upstream connection timed out",
        ],
    }


LOGS_TOOL_DEFINITION = {
    "name": "get_logs",
    "description": "Retrieve recent application error logs for a given service.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "The name of the service to retrieve logs for",
            },
            "minutes": {
                "type": "integer",
                "description": "The lookback window in minutes (default: 30)",
            },
        },
        "required": ["service"],
    },
}
