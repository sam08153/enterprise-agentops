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
