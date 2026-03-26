"""Dashboard logs router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_permission
from app.models.dashboard_log import DashboardLog
from app.models.user import User
from app.schemas.logs import DashboardLogResponse, LogCategory

router = APIRouter(prefix="/logs", tags=["logs"])


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
    return [DashboardLogResponse.model_validate(item) for item in result.scalars().all()]
