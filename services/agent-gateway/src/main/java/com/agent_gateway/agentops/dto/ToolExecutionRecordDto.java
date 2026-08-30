package com.agent_gateway.agentops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ToolExecutionRecordDto(
    @JsonProperty("tool_name") String toolName,
    @JsonProperty("input") String input,
    @JsonProperty("output") String output,
    @JsonProperty("status") String status,
    @JsonProperty("started_at") String startedAt,
    @JsonProperty("completed_at") String completedAt,
    @JsonProperty("duration_ms") int durationMs
) {
}
