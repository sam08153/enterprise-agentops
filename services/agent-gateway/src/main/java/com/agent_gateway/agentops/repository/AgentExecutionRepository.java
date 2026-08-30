package com.agent_gateway.agentops.repository;

import com.agent_gateway.agentops.model.AgentExecution;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;
import java.util.UUID;

@Repository
public interface AgentExecutionRepository extends JpaRepository<AgentExecution, UUID> {
    List<AgentExecution> findByIncidentId(UUID incidentId);
}
