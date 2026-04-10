"""FastAPI application factory."""

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select, update

from app.cache import close_redis, get_redis
from app.config import get_settings
from app.database import AsyncSessionLocal, engine
from app.models.scrape_job import ScrapeJob
from app.models.user import User
from app.routers import (
    ai,
    assets,
    auth,
    dashboard,
    ddm,
    devices,
    health,
    knowledge,
    logs,
    migrator,
    package_sync,
    patches,
    policies,
    servers,
    smart_groups,
    system,
    users,
)
from app.services.auth import AuthService
from app.services.dashboard_logs import write_dashboard_log
from app.services.jamf.sync import sync_all_servers
from app.services.llm import describe_embedding_target, describe_llm_target

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle."""
    settings = get_settings()
    logger.info(
        "Starting Jamf AI Dashboard",
        provider=settings.ai_provider,
        model=describe_llm_target(settings),
        embedding_provider=settings.embedding_provider,
        embedding_model=describe_embedding_target(settings),
    )

    # Warm up Redis connection
    await get_redis()

    # Mark any jobs that were left in 'running' state (e.g. from a previous crash/restart) as failed
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(ScrapeJob)
            .where(ScrapeJob.status == "running")
            .values(
                status="failed",
                error="Interrupted: service was restarted while job was running",
                finished_at=datetime.now(UTC),
            )
            .returning(ScrapeJob.id, ScrapeJob.domain)
        )
        interrupted = result.fetchall()
        await session.commit()
        if interrupted:
            for job_id, domain in interrupted:
                logger.warning(
                    "Marked interrupted scrape job as failed",
                    job_id=str(job_id),
                    domain=domain,
                )

    # Start background sync scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        sync_all_servers,
        trigger="interval",
        minutes=settings.sync_interval_minutes,
        id="sync_all_servers",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info(
        "Sync scheduler started",
        interval_minutes=settings.sync_interval_minutes,
    )

    yield

    # Graceful shutdown
    logger.info("Shutting down")
    scheduler.shutdown(wait=False)
    await close_redis()
    await engine.dispose()


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
        allow_origin_regex=settings.cors_origin_regex,
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

    @application.middleware("http")
    async def dashboard_audit_middleware(request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        if path in {"/api/v1/health", "/metrics", "/docs", "/openapi.json", "/redoc"}:
            return response
        if path.startswith("/api/v1/logs"):
            return response
        if request.method == "OPTIONS":
            return response

        category = "action"
        if path.startswith("/api/v1/servers"):
            category = "server"
        elif path.startswith("/api/v1/auth"):
            category = "login"

        user_id = None
        username = None
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            payload = AuthService._decode_token(token)
            if payload and payload.get("type") == "access":
                try:
                    uid = payload.get("sub")
                    if uid:
                        parsed_uid = uuid.UUID(uid)
                        async with AsyncSessionLocal() as db:
                            user = (
                                await db.execute(select(User).where(User.id == parsed_uid))
                            ).scalar_one_or_none()
                            if user:
                                user_id = user.id
                                username = user.username
                except Exception:
                    pass

        await write_dashboard_log(
            category=category,
            action=f"{request.method} {path}",
            message=f"{request.method} {path} -> {response.status_code}",
            method=request.method,
            path=path,
            status_code=response.status_code,
            user_id=user_id,
            username=username,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={"query": dict(request.query_params)},
        )
        return response

    # ── Routers ───────────────────────────────────────────────
    API_PREFIX = "/api/v1"
    application.include_router(health.router, prefix=API_PREFIX)
    application.include_router(auth.router, prefix=API_PREFIX)
    application.include_router(servers.router, prefix=API_PREFIX)
    application.include_router(devices.router, prefix=API_PREFIX)
    application.include_router(ddm.router, prefix=API_PREFIX)
    application.include_router(policies.router, prefix=API_PREFIX)
    application.include_router(patches.router, prefix=API_PREFIX)
    application.include_router(smart_groups.router, prefix=API_PREFIX)
    application.include_router(dashboard.router, prefix=API_PREFIX)
    application.include_router(assets.router, prefix=API_PREFIX)
    application.include_router(knowledge.router, prefix=API_PREFIX)
    application.include_router(logs.router, prefix=API_PREFIX)
    application.include_router(migrator.router, prefix=API_PREFIX)
    application.include_router(package_sync.router, prefix=API_PREFIX)
    application.include_router(users.router, prefix=API_PREFIX)
    application.include_router(ai.router, prefix=API_PREFIX)

    application.include_router(system.router, prefix=API_PREFIX)

    return application


app = create_app()
