package com.agent_gateway.agentops.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record AgentRcaResponse(
    @JsonProperty("incident_id") String incidentId,
    @JsonProperty("service") String service,
    @JsonProperty("summary") String summary,
    @JsonProperty("root_cause") String rootCause,
    @JsonProperty("confidence") double confidence,
    @JsonProperty("evidence") List<String> evidence,
    @JsonProperty("recommended_actions") List<String> recommendedActions,
    @JsonProperty("actions_executed") List<String> actionsExecuted,

    // Observability metadata
    @JsonProperty("input_tokens") int inputTokens,
    @JsonProperty("output_tokens") int outputTokens,
    @JsonProperty("tool_calls") int toolCalls,
    @JsonProperty("tool_executions") List<ToolExecutionRecordDto> toolExecutions
) {
}
