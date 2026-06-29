import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    alerts,
    auth,
    background,
    doctor_access,
    health,
    intake,
    medications,
    outputs,
    patients,
    reports,
    shared,
    symptoms,
    vitals,
)
from app.core.config import get_settings
from app.vectorstore.collections import bootstrap_collections

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Engine is created at import; warm the Chroma collections (best-effort).
    try:
        bootstrap_collections()
    except Exception:
        logger.warning("Chroma collection bootstrap failed at startup", exc_info=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Personal Health Intelligence Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix=settings.API_PREFIX)
    app.include_router(auth.router, prefix=settings.API_PREFIX)
    app.include_router(patients.router, prefix=settings.API_PREFIX)
    app.include_router(background.router, prefix=settings.API_PREFIX)
    app.include_router(medications.router, prefix=settings.API_PREFIX)
    app.include_router(vitals.router, prefix=settings.API_PREFIX)
    app.include_router(symptoms.router, prefix=settings.API_PREFIX)
    app.include_router(reports.router, prefix=settings.API_PREFIX)
    app.include_router(intake.router, prefix=settings.API_PREFIX)
    app.include_router(outputs.router, prefix=settings.API_PREFIX)
    app.include_router(alerts.router, prefix=settings.API_PREFIX)
    app.include_router(doctor_access.router, prefix=settings.API_PREFIX)
    app.include_router(shared.router, prefix=settings.API_PREFIX)
    return app


app = create_app()
