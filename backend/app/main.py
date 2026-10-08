from app.api.ai import router as ai_router
from app.api.integrations import router as integrations_router
from app.api.analytics import reports as reports_router, extracts as extracts_router
from app.api.imports import router as imports_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.fbp import router as fbp_router
from app.api.payroll import router as payroll_router
from app.api.auth import router as auth_router
from app.api.core_hr import router as core_hr_router, hr_error_handler
from app.services.core_hr.common import HRError
from app.api.health import router as health_router
from app.core.config import settings


app = FastAPI(
    title="FusionHCM 360 API",
    version="0.1.0",
    description="HCM simulation API for synthetic workforce data.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=True,
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(core_hr_router)
app.include_router(payroll_router)
app.include_router(fbp_router)
app.include_router(imports_router)
app.include_router(reports_router)
app.include_router(extracts_router)
app.include_router(integrations_router)
app.include_router(ai_router)
app.add_exception_handler(HRError, hr_error_handler)


@app.get("/")
def root():
    return {
        "name": "FusionHCM 360 API",
        "status": "running",
    }
