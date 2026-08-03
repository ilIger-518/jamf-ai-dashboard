"""Dashboard logs router."""

import json
from collections.abc import Iterable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission
from app.models.dashboard_log import DashboardLog
from app.models.user import User
from app.schemas.logs import DashboardLogResponse, LogCategory

router = APIRouter(prefix="/logs", tags=["logs"])


def _normalize_details(details: object) -> dict | None:
    if details is None:
        return None
    if isinstance(details, dict):
        return details
    if isinstance(details, str):
        try:
            parsed = json.loads(details)
        except json.JSONDecodeError:
            return {"raw": details}
        return parsed if isinstance(parsed, dict) else {"raw": details}
    return {"raw": str(details)}


def _serialize_logs(items: Iterable[DashboardLog]) -> list[DashboardLogResponse]:
    serialized: list[DashboardLogResponse] = []
    for item in items:
        payload = {
            "id": item.id,
            "category": item.category,
            "action": item.action,
            "level": item.level,
            "message": item.message,
            "method": item.method,
            "path": item.path,
            "status_code": item.status_code,
            "user_id": item.user_id,
            "username": item.username,
            "ip_address": item.ip_address,
            "user_agent": item.user_agent,
            "details": _normalize_details(item.details),
            "created_at": item.created_at,
        }
        try:
            serialized.append(DashboardLogResponse.model_validate(payload))
        except ValidationError:
            continue
    return serialized


@router.get("", response_model=list[DashboardLogResponse])
async def list_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission("settings.manage"))],
    category: LogCategory | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[DashboardLogResponse]:
    # Skip legacy rows left behind by older dashboard_logs schemas that do not satisfy
    # the current response contract.
    query = (
        select(DashboardLog)
        .where(
            DashboardLog.category.is_not(None),
            DashboardLog.action.is_not(None),
            DashboardLog.level.is_not(None),
            DashboardLog.message.is_not(None),
        )
        .order_by(desc(DashboardLog.created_at))
        .limit(limit)
    )
    if category:
        query = query.where(DashboardLog.category == category)
    result = await db.execute(query)
    return _serialize_logs(result.scalars().all())
