"""Smart groups router."""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession
from app.models.smart_group import SmartGroup
from app.schemas.smart_groups import PagedSmartGroups, SmartGroupResponse

router = APIRouter(prefix="/smart-groups", tags=["smart-groups"])


@router.get("", response_model=PagedSmartGroups)
async def list_smart_groups(
    db: DBSession,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    server_id: uuid.UUID | None = Query(None),
) -> PagedSmartGroups:
    q = select(SmartGroup)
    if search:
        q = q.where(SmartGroup.name.ilike(f"%{search}%"))
    if server_id:
        q = q.where(SmartGroup.server_id == server_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.order_by(SmartGroup.name).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(q)).scalars().all()

    return PagedSmartGroups(
        items=[SmartGroupResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{group_id}", response_model=SmartGroupResponse)
async def get_smart_group(group_id: uuid.UUID, db: DBSession, _: CurrentUser) -> SmartGroupResponse:
    result = await db.execute(select(SmartGroup).where(SmartGroup.id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Smart group not found")
    return SmartGroupResponse.model_validate(group)
