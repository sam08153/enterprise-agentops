package com.agent_gateway.agentops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotNull;
import java.util.UUID;

public record InvestigateRequest(
    @NotNull(message = "Incident ID is required")
    @JsonProperty("incidentId") UUID incidentId
) {
}
