import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.anyio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "ai-service"
    assert data["status"] == "UP"


@pytest.mark.anyio
async def test_analyze():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/analyze",
            json={
                "incident_id": "inc-001",
                "title": "Payment service errors",
                "description": "5xx increased after deployment",
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "RECEIVED"
    assert "next phase" in data["message"]
