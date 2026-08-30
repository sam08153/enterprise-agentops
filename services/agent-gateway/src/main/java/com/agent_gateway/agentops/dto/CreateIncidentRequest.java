package com.agent_gateway.agentops.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.UUID;

public record CreateIncidentRequest(
    @NotNull(message = "Tenant ID is required")
    UUID tenantId,

    @NotBlank(message = "Title is required")
    @Size(max = 500, message = "Title cannot exceed 500 characters")
    String title,

    @NotBlank(message = "Description is required")
    String description,

    String severity
) {
}
