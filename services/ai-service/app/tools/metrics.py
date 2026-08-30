def get_metrics(service: str) -> dict:
    """Retrieve current and baseline performance metrics for a service."""
    return {
        "service": service,
        "error_rate_before": "1.2%",
        "error_rate_current": "18%",
        "latency_p99_before": "180ms",
        "latency_p99_current": "920ms",
        "cpu_utilization": "54%",
        "memory_utilization": "61%",
        "throughput_before": "1200 rps",
        "throughput_current": "980 rps",
    }


METRICS_TOOL_DEFINITION = {
    "name": "get_metrics",
    "description": "Retrieve performance metrics for a service including error rate, latency, CPU and memory usage.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service": {
                "type": "string",
                "description": "The name of the service to retrieve metrics for",
            }
        },
        "required": ["service"],
    },
}
