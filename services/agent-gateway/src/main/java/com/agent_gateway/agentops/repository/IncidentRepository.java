package com.agent_gateway.agentops.repository;

import com.agent_gateway.agentops.model.Incident;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface IncidentRepository extends JpaRepository<Incident, UUID> {
    List<Incident> findAllByOrderByCreatedAtDesc();
    List<Incident> findByTenantIdOrderByCreatedAtDesc(UUID tenantId);
}
