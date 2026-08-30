package com.agent_gateway.agentops.dto;

public record HealthResponse(
    String service,
    String status
) {
}
