package com.agent_gateway.agentops.dto;

import java.util.UUID;

public record CreateIncidentResponse(
    UUID incidentId,
    String status
) {
}
