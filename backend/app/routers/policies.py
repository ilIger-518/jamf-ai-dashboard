"""Policies router."""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession
from app.models.policy import Policy
from app.schemas.policies import PagedPolicies, PolicyResponse

router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("", response_model=PagedPolicies)
async def list_policies(
    db: DBSession,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    server_id: uuid.UUID | None = Query(None),
    enabled_only: bool = Query(False),
) -> PagedPolicies:
    q = select(Policy)
    if search:
        q = q.where(Policy.name.ilike(f"%{search}%"))
    if server_id:
        q = q.where(Policy.server_id == server_id)
    if enabled_only:
        q = q.where(Policy.enabled.is_(True))

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.order_by(Policy.name).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(q)).scalars().all()

    return PagedPolicies(
        items=[PolicyResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(policy_id: uuid.UUID, db: DBSession, _: CurrentUser) -> PolicyResponse:
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    policy = result.scalar_one_or_none()
    if policy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return PolicyResponse.model_validate(policy)
