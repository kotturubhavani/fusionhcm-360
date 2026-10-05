from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings


app = FastAPI(
    title="FusionHCM 360 API",
    version="0.1.0",
    description="Backend API for the FusionHCM 360 portfolio project.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=[],
)

app.include_router(health_router)


@app.get("/")
def root():
    return {
        "name": "FusionHCM 360 API",
        "status": "running"
    }
