package com.agent_gateway.agentops.dto;

import com.agent_gateway.agentops.model.Incident;

import java.time.Instant;
import java.util.UUID;

public record IncidentResponse(
    UUID id,
    UUID tenantId,
    String title,
    String description,
    String status,
    String severity,
    Instant createdAt
) {
    public static IncidentResponse fromEntity(Incident incident) {
        return new IncidentResponse(
            incident.getId(),
            incident.getTenant().getId(),
            incident.getTitle(),
            incident.getDescription(),
            incident.getStatus(),
            incident.getSeverity(),
            incident.getCreatedAt()
        );
    }
}
