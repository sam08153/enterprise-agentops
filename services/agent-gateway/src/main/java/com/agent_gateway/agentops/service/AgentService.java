package com.agent_gateway.agentops.service;

import com.agent_gateway.agentops.dto.AgentRcaResponse;
import com.agent_gateway.agentops.dto.InvestigateRequest;
import com.agent_gateway.agentops.dto.ToolExecutionRecordDto;
import com.agent_gateway.agentops.model.AgentExecution;
import com.agent_gateway.agentops.model.ToolExecution;
import com.agent_gateway.agentops.repository.AgentExecutionRepository;
import com.agent_gateway.agentops.repository.ToolExecutionRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.server.ResponseStatusException;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@Service
@Transactional
public class AgentService {

    private final AgentExecutionRepository agentExecutionRepository;
    private final ToolExecutionRepository toolExecutionRepository;
    private final RestTemplate restTemplate;
    private final String aiServiceUrl;

    public AgentService(
            AgentExecutionRepository agentExecutionRepository,
            ToolExecutionRepository toolExecutionRepository,
            @Value("${ai-service.url:http://localhost:8081}") String aiServiceUrl) {
        this.agentExecutionRepository = agentExecutionRepository;
        this.toolExecutionRepository = toolExecutionRepository;
        this.restTemplate = new RestTemplate();
        this.aiServiceUrl = aiServiceUrl;
    }

    public AgentRcaResponse investigate(InvestigateRequest request) {
        UUID incidentId = request.incidentId();

        // 1. Create and save AgentExecution record in RUNNING status
        AgentExecution agentExecution = new AgentExecution();
        agentExecution.setIncidentId(incidentId);
        agentExecution.setAgentName("Production Incident Investigation Agent");
        agentExecution.setStatus("RUNNING");
        agentExecution.setStartedAt(Instant.now());
        agentExecution = agentExecutionRepository.save(agentExecution);

        try {
            // 2. Call the AI Service via RestTemplate
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);

            HttpEntity<Map<String, String>> entity = new HttpEntity<>(
                Map.of("incident_id", incidentId.toString()),
                headers
            );

            AgentRcaResponse rcaResponse = restTemplate.postForObject(
                aiServiceUrl + "/api/v1/agent/investigate",
                entity,
                AgentRcaResponse.class
            );

            if (rcaResponse == null) {
                throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Empty response from AI Service");
            }

            // 3. Update the AgentExecution record
            agentExecution.setStatus("SUCCESS");
            agentExecution.setCompletedAt(Instant.now());
            agentExecution.setInputTokens(rcaResponse.inputTokens());
            agentExecution.setOutputTokens(rcaResponse.outputTokens());
            agentExecution.setToolCalls(rcaResponse.toolCalls());
            agentExecution = agentExecutionRepository.save(agentExecution);

            // 4. Save each ToolExecution record
            if (rcaResponse.toolExecutions() != null) {
                for (ToolExecutionRecordDto toolDto : rcaResponse.toolExecutions()) {
                    ToolExecution toolExecution = new ToolExecution();
                    toolExecution.setAgentExecution(agentExecution);
                    toolExecution.setToolName(toolDto.toolName());
                    toolExecution.setInput(toolDto.input());
                    toolExecution.setOutput(toolDto.output());
                    toolExecution.setStatus(toolDto.status());
                    try {
                        toolExecution.setStartedAt(Instant.parse(toolDto.startedAt()));
                    } catch (Exception e) {
                        toolExecution.setStartedAt(Instant.now());
                    }
                    try {
                        toolExecution.setCompletedAt(Instant.parse(toolDto.completedAt()));
                    } catch (Exception e) {
                        toolExecution.setCompletedAt(Instant.now());
                    }
                    toolExecution.setDurationMs(toolDto.durationMs());
                    toolExecutionRepository.save(toolExecution);
                }
            }

            return rcaResponse;

        } catch (Exception e) {
            // 5. Update AgentExecution to FAILED if exception occurred
            agentExecution.setStatus("FAILED");
            agentExecution.setCompletedAt(Instant.now());
            agentExecution.setErrorMessage(e.getMessage());
            agentExecutionRepository.save(agentExecution);

            throw new ResponseStatusException(
                    HttpStatus.INTERNAL_SERVER_ERROR,
                    "Agent investigation failed: " + e.getMessage(),
                    e
            );
        }
    }
}
