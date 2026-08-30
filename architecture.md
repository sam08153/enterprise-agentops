# Enterprise AgentOps Platform Architecture

This document describes the high-level architecture of the Enterprise AgentOps Platform, focusing on the flow from the user interface down to agent execution and orchestration.

## Architecture Topology

```mermaid
graph TD
    %% Clients
    ReactApp["React Frontend (UI)"]

    %% Gateway Layer
    subgraph Gateway ["Java Agent Gateway (Spring Boot)"]
        AuthFilter["1. Authentication (JWT/API Key)"]
        AuthzInterceptor["2. Authorization (RBAC)"]
        TenantResolver["3. Tenant Management (Context Resolver)"]
        RateLimiter["4. Rate Limiting (Redis Token Bucket)"]
        A2AEngine["5. A2A (Agent-to-Agent Communication)"]
        AgentRouter["6. Agent Routing / Dispatcher"]
    end

    %% Execution Layer
    subgraph Execution ["Agent & AI Service Layer"]
        FastAPIService["AI Service (Python/FastAPI)"]
        TemporalWorker["Durable Workflows (Temporal)"]
        MCPServer["MCP Tool Integrations"]
    end

    %% Storage Layer
    subgraph Storage ["Infrastructure & Storage"]
        PostgresDB["PostgreSQL (vector)"]
        RedisCache["Redis (Cache/Rate Limits)"]
    end

    %% Client connection
    ReactApp -->|HTTP/WebSockets| AuthFilter
    
    %% Gateway Filters pipeline
    AuthFilter --> AuthzInterceptor
    AuthzInterceptor --> TenantResolver
    TenantResolver --> RateLimiter
    RateLimiter --> A2AEngine
    A2AEngine --> AgentRouter

    %% Routing to execution services
    AgentRouter -->|HTTP/REST| FastAPIService
    AgentRouter -->|gRPC/SDK| TemporalWorker
    AgentRouter -->|MCP Protocol| MCPServer

    %% Database & Cache access
    Gateway -->|JPA| PostgresDB
    Gateway -->|Jedis/Lettuce| RedisCache
    FastAPIService -->|pgvector| PostgresDB
```

---

## 1. Authentication & Security
- **JWT Authentication**: Validates tokens issued by identity providers (e.g., Keycloak, Cognito, or a local service).
- **API Keys**: Extends access to external systems or integrations, resolving key ownership to a tenant and service context.

## 2. Authorization (RBAC)
- **Roles**: Defines scopes like `admin`, `developer`, `operator`, and `viewer`.
- **Permissions**: Access constraints at resource levels (`incident:create`, `agent:invoke`, `document:write`).

## 3. Tenant Management
- **Multi-Tenancy**: Resolves the tenant context (e.g. from subdomains, headers like `X-Tenant-ID`, or JWT claims).
- **Isolation**: Ensures all DB connections, cache keys, and execution logs are partitioned by the resolved `tenant_id`.

## 4. Rate Limiting
- **Redis-Backed Token Bucket**: Implements per-tenant and per-user rate limits to prevent runaway loops (e.g., infinite agent recursive invocations).

## 5. Agent-to-Agent (A2A) Communication
- **Mailbox Pattern**: Provides asynchronous messaging between agents.
- **Event Mesh**: Manages reliable delivery of messages using Redis Pub/Sub or transactional outbox.

## 6. Agent Routing & Tool Dispatching
- **Intelligent Dispatch**: Dynamically routes task executions to the `FastAPI AI Service` or background `Temporal` workflows.
- **Model Context Protocol (MCP)**: Acts as the client orchestrating external tool invocation safely.
