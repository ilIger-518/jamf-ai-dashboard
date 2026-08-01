"""Health check router."""

import inspect
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.cache import get_redis
from app.database import AsyncSessionLocal


class DependencyStatus(BaseModel):
    status: str
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    database: DependencyStatus
    redis: DependencyStatus
    uptime_seconds: int


router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Liveness + dependency health check")
async def health() -> HealthResponse:
    db_status = "ok"
    redis_status = "ok"
    db_detail: Optional[str] = None
    redis_detail: Optional[str] = None

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:
        db_status = "error"
        db_detail = str(exc)

    try:
        redis = await get_redis()
        ping_result = redis.ping()
        if inspect.isawaitable(ping_result):
            await ping_result
    except Exception as exc:
        redis_status = "error"
        redis_detail = str(exc)

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        database=DependencyStatus(status=db_status, detail=db_detail),
        redis=DependencyStatus(status=redis_status, detail=redis_detail),
        uptime_seconds=0,
    )