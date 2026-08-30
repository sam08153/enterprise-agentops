from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.routers import health, analyze, investigate, rag


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print(f"Starting {settings.app_name} v{settings.app_version}")
    yield
    print(f"Shutting down {settings.app_name}")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI analysis service for enterprise AgentOps platform",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(investigate.router)
app.include_router(rag.router)
