from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Engine is created at import; Chroma client is lazily cached on first use.
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Personal Health Intelligence Agent",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(health.router, prefix=settings.API_PREFIX)
    return app


app = create_app()
