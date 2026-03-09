"""Patches router."""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession
from app.models.patch import PatchTitle
from app.schemas.patches import PagedPatches, PatchResponse

router = APIRouter(prefix="/patches", tags=["patches"])


@router.get("", response_model=PagedPatches)
async def list_patches(
    db: DBSession,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    server_id: uuid.UUID | None = Query(None),
) -> PagedPatches:
    q = select(PatchTitle)
    if search:
        q = q.where(PatchTitle.software_title.ilike(f"%{search}%"))
    if server_id:
        q = q.where(PatchTitle.server_id == server_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.order_by(PatchTitle.software_title).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(q)).scalars().all()

    return PagedPatches(
        items=[PatchResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{patch_id}", response_model=PatchResponse)
async def get_patch(patch_id: uuid.UUID, db: DBSession, _: CurrentUser) -> PatchResponse:
    result = await db.execute(select(PatchTitle).where(PatchTitle.id == patch_id))
    patch = result.scalar_one_or_none()
    if patch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patch title not found")
    return PatchResponse.model_validate(patch)
