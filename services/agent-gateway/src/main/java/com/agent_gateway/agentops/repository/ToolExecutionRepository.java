package com.agent_gateway.agentops.repository;

import com.agent_gateway.agentops.model.ToolExecution;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;
import java.util.UUID;

@Repository
public interface ToolExecutionRepository extends JpaRepository<ToolExecution, UUID> {
    List<ToolExecution> findByAgentExecutionId(UUID agentExecutionId);
}
