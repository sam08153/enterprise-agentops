package com.agent_gateway.agentops.controller;

import com.agent_gateway.agentops.dto.AgentRcaResponse;
import com.agent_gateway.agentops.dto.InvestigateRequest;
import com.agent_gateway.agentops.service.AgentService;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/agent")
public class AgentController {

    private final AgentService agentService;

    public AgentController(AgentService agentService) {
        this.agentService = agentService;
    }

    @PostMapping("/investigate")
    public ResponseEntity<AgentRcaResponse> investigate(@Valid @RequestBody InvestigateRequest request) {
        AgentRcaResponse response = agentService.investigate(request);
        return ResponseEntity.ok(response);
    }
}
