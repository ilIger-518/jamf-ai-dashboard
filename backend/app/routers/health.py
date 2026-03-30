"""Health check router."""

import inspect

from fastapi import APIRouter
from pydantic import BaseModel

from app.cache import get_redis
from app.database import AsyncSessionLocal

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str


@router.get("", response_model=HealthResponse, summary="Liveness + dependency health check")
async def health() -> HealthResponse:
    db_status = "ok"
    redis_status = "ok"

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        redis = await get_redis()
        ping_result = redis.ping()
        if inspect.isawaitable(ping_result):
            await ping_result
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(status=overall, database=db_status, redis=redis_status)
