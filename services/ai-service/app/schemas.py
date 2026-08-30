from pydantic import BaseModel


class HealthResponse(BaseModel):
    service: str
    status: str


class AnalyzeRequest(BaseModel):
    incident_id: str
    title: str
    description: str


class AnalyzeResponse(BaseModel):
    status: str
    message: str


class RagSearchRequest(BaseModel):
    query: str
    tenant_id: str = "demo"


class RagSearchResult(BaseModel):
    source: str
    score: float
    content: str


class RagSearchResponse(BaseModel):
    query: str
    tenant_id: str
    results: list[RagSearchResult]
