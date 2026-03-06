"""FastAPI application factory."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from app.cache import close_redis, get_redis
from app.config import get_settings
from app.database import engine
from app.routers import ai, auth, dashboard, devices, health, patches, policies, servers, smart_groups

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info("Starting Jamf AI Dashboard", model=settings.ollama_model)

    # Warm up Redis connection
    await get_redis()

    yield

    # Graceful shutdown
    logger.info("Shutting down")
    await close_redis()
    await engine.dispose()  # type: ignore[union-attr]


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Jamf AI Dashboard API",
        description="Self-hosted Jamf Pro monitoring dashboard with AI assistant",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ── CORS ──────────────────────────────────────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Prometheus metrics ────────────────────────────────────
    Instrumentator().instrument(application).expose(application, endpoint="/metrics")

    # ── Global exception handler ──────────────────────────────
    @application.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred.",
            },
        )

    # ── Routers ───────────────────────────────────────────────
    API_PREFIX = "/api/v1"
    application.include_router(health.router, prefix=API_PREFIX)
    application.include_router(auth.router, prefix=API_PREFIX)
    application.include_router(servers.router, prefix=API_PREFIX)
    application.include_router(devices.router, prefix=API_PREFIX)
    application.include_router(policies.router, prefix=API_PREFIX)
    application.include_router(patches.router, prefix=API_PREFIX)
    application.include_router(smart_groups.router, prefix=API_PREFIX)
    application.include_router(dashboard.router, prefix=API_PREFIX)
    application.include_router(ai.router, prefix=API_PREFIX)

    return application


app = create_app()
