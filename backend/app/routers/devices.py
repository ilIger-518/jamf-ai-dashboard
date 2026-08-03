"""Devices router."""

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DBSession
from app.models.device import Device
from app.schemas.devices import DeviceResponse, PagedDevices

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=PagedDevices)
async def list_devices(
    db: DBSession,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    server_id: uuid.UUID | None = Query(None),
    managed_only: bool = Query(False),
) -> PagedDevices:
    q = select(Device)
    if search:
        pattern = f"%{search}%"
        q = q.where(
            Device.name.ilike(pattern)
            | Device.serial_number.ilike(pattern)
            | Device.username.ilike(pattern)
        )
    if server_id:
        q = q.where(Device.server_id == server_id)
    if managed_only:
        q = q.where(Device.is_managed.is_(True))

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.order_by(Device.name).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(q)).scalars().all()

    return PagedDevices(
        items=[DeviceResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(device_id: uuid.UUID, db: DBSession, _: CurrentUser) -> DeviceResponse:
    result = await db.execute(
        select(Device).options(selectinload(Device.server)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    response = DeviceResponse.model_validate(device)
    if device.server:
        response.server_url = device.server.url.rstrip("/")
    return response
