package com.agent_gateway.agentops.controller;

import com.agent_gateway.agentops.dto.CreateIncidentRequest;
import com.agent_gateway.agentops.dto.CreateIncidentResponse;
import com.agent_gateway.agentops.dto.IncidentResponse;
import com.agent_gateway.agentops.service.IncidentService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/incidents")
public class IncidentController {

    private final IncidentService incidentService;

    public IncidentController(IncidentService incidentService) {
        this.incidentService = incidentService;
    }

    @PostMapping
    public ResponseEntity<CreateIncidentResponse> createIncident(@Valid @RequestBody CreateIncidentRequest request) {
        CreateIncidentResponse response = incidentService.createIncident(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }

    @GetMapping
    public ResponseEntity<List<IncidentResponse>> getAllIncidents(
        @RequestParam(value = "tenantId", required = false) UUID tenantId
    ) {
        if (tenantId != null) {
            return ResponseEntity.ok(incidentService.getIncidentsByTenant(tenantId));
        }
        return ResponseEntity.ok(incidentService.getAllIncidents());
    }

    @GetMapping("/{id}")
    public ResponseEntity<IncidentResponse> getIncidentById(@PathVariable("id") UUID id) {
        return incidentService.getIncidentById(id)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
