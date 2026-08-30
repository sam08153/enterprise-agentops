package com.agent_gateway.agentops.repository;

import com.agent_gateway.agentops.model.DocumentChunk;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface DocumentChunkRepository extends JpaRepository<DocumentChunk, UUID> {
    
    List<DocumentChunk> findByDocumentId(UUID documentId);

    @Query(value = "SELECT dc.* FROM document_chunks dc " +
                   "JOIN documents d ON dc.document_id = d.id " +
                   "WHERE d.tenant_id = :tenantId " +
                   "ORDER BY dc.embedding <=> CAST(:embedding AS vector) " +
                   "LIMIT :limit", nativeQuery = true)
    List<DocumentChunk> findSimilarChunks(
        @Param("tenantId") UUID tenantId,
        @Param("embedding") String embedding,
        @Param("limit") int limit
    );
}
