package com.agent_gateway.agentops;

import com.agent_gateway.agentops.model.Tenant;
import com.agent_gateway.agentops.repository.TenantRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

import static org.hamcrest.Matchers.is;
import static org.hamcrest.Matchers.notNullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
class IncidentControllerTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    @Autowired
    private TenantRepository tenantRepository;

    private MockMvc mockMvc;
    private Tenant testTenant;

    @BeforeEach
    void setUp() {
        this.mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext).build();
        testTenant = tenantRepository.findByName("test-tenant")
            .orElseGet(() -> tenantRepository.save(new Tenant("test-tenant")));
    }

    @Test
    void shouldReturnHealthStatus() throws Exception {
        mockMvc.perform(get("/api/v1/health"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.service", is("agent-gateway")))
            .andExpect(jsonPath("$.status", is("UP")));
    }

    @Test
    void shouldCreateIncidentSuccessfully() throws Exception {
        String requestBody = String.format("""
            {
              "tenantId": "%s",
              "title": "Payment service error rate increased",
              "description": "5xx errors increased to 18%% after deployment",
              "severity": "HIGH"
            }
            """, testTenant.getId());

        mockMvc.perform(post("/api/v1/incidents")
                .contentType(MediaType.APPLICATION_JSON)
                .content(requestBody))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.incidentId", notNullValue()))
            .andExpect(jsonPath("$.status", is("OPEN")));
    }
}
