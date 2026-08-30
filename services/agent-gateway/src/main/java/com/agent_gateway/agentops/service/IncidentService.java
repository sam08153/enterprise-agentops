package com.agent_gateway.agentops.service;

import com.agent_gateway.agentops.dto.CreateIncidentRequest;
import com.agent_gateway.agentops.dto.CreateIncidentResponse;
import com.agent_gateway.agentops.dto.IncidentResponse;
import com.agent_gateway.agentops.model.Incident;
import com.agent_gateway.agentops.model.Tenant;
import com.agent_gateway.agentops.repository.IncidentRepository;
import com.agent_gateway.agentops.repository.TenantRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Service
@Transactional
public class IncidentService {

    private final IncidentRepository incidentRepository;
    private final TenantRepository tenantRepository;

    public IncidentService(IncidentRepository incidentRepository, TenantRepository tenantRepository) {
        this.incidentRepository = incidentRepository;
        this.tenantRepository = tenantRepository;
    }

    public CreateIncidentResponse createIncident(CreateIncidentRequest request) {
        Tenant tenant = tenantRepository.findById(request.tenantId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Tenant not found: " + request.tenantId()
            ));

        Incident incident = new Incident(
            tenant,
            request.title(),
            request.description(),
            "OPEN",
            request.severity()
        );

        Incident saved = incidentRepository.save(incident);
        return new CreateIncidentResponse(saved.getId(), saved.getStatus());
    }

    @Transactional(readOnly = true)
    public List<IncidentResponse> getAllIncidents() {
        return incidentRepository.findAllByOrderByCreatedAtDesc()
            .stream()
            .map(IncidentResponse::fromEntity)
            .toList();
    }

    @Transactional(readOnly = true)
    public List<IncidentResponse> getIncidentsByTenant(UUID tenantId) {
        return incidentRepository.findByTenantIdOrderByCreatedAtDesc(tenantId)
            .stream()
            .map(IncidentResponse::fromEntity)
            .toList();
    }

    @Transactional(readOnly = true)
    public Optional<IncidentResponse> getIncidentById(UUID id) {
        return incidentRepository.findById(id)
            .map(IncidentResponse::fromEntity);
    }
}
