"""DDM (Declarative Device Management) router.

Provides endpoints to:
  - List managed devices that have a management_id (required for DDM queries)
  - Fetch live DDM status-items for a single device from Jamf Pro
  - Force-sync DDM declarations to a device
"""

import uuid

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies import CurrentUser, DBSession
from app.models.device import Device
from app.models.server import JamfServer
from app.schemas.ddm import DDMDeviceListItem, DDMStatusResponse, DDMSyncResponse, PagedDDMDevices
from app.services.encryption import decrypt
from app.services.jamf.sync import _get_oauth_token

router = APIRouter(prefix="/ddm", tags=["ddm"])

_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_server_and_token(db: AsyncSession, server_id: uuid.UUID) -> tuple[JamfServer, str]:
    """Return the JamfServer row and a fresh OAuth bearer token."""
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    if not server.is_active:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Server is inactive"
        )

    client_id = decrypt(server.client_id)
    client_secret = decrypt(server.client_secret)

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        token = await _get_oauth_token(client, server.url.rstrip("/"), client_id, client_secret)

    return server, token


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/devices", response_model=PagedDDMDevices)
async def list_ddm_devices(
    db: DBSession,
    _: CurrentUser,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str | None = Query(None),
    server_id: uuid.UUID | None = Query(None),
) -> PagedDDMDevices:
    """List devices that have a management_id (DDM-capable devices)."""
    q = select(Device).where(Device.management_id.is_not(None))

    if search:
        pattern = f"%{search}%"
        q = q.where(
            Device.name.ilike(pattern)
            | Device.serial_number.ilike(pattern)
            | Device.username.ilike(pattern)
        )
    if server_id:
        q = q.where(Device.server_id == server_id)

    total_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = total_result.scalar_one()

    q = q.order_by(Device.name).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(q)).scalars().all()

    return PagedDDMDevices(
        items=[DDMDeviceListItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/devices/{device_id}/status", response_model=DDMStatusResponse)
async def get_ddm_device_status(
    device_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,
) -> DDMStatusResponse:
    """Fetch live DDM status-items for a device directly from Jamf Pro."""
    result = await db.execute(
        select(Device).options(selectinload(Device.server)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if not device.management_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Device does not have a management_id; DDM may not be enabled on this device.",
        )

    server = device.server
    client_id = decrypt(server.client_id)
    client_secret = decrypt(server.client_secret)
    base_url = server.url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            token = await _get_oauth_token(client, base_url, client_id, client_secret)

            resp = await client.get(
                f"{base_url}/api/v1/ddm/{device.management_id}/status-items",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cannot reach Jamf Pro server",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timed out connecting to Jamf Pro",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="DDM status not found on Jamf Pro; DDM may not be enabled on this device.",
        )
    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Insufficient Jamf Pro API privileges to read DDM status. "
            "Ensure 'Read Computers' and DDM privileges are granted.",
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jamf Pro returned {resp.status_code}: {resp.text[:200]}",
        )

    raw = resp.json()
    status_items: list[dict] = []
    if isinstance(raw, dict):
        fetched = raw.get("statusItems") or raw.get("results") or []
        if isinstance(fetched, list):
            status_items = fetched
    elif isinstance(raw, list):
        status_items = raw

    return DDMStatusResponse(
        device_id=device_id,
        management_id=device.management_id,
        status_items=status_items,
        raw=raw if isinstance(raw, dict) else {"results": raw},
    )


@router.post(
    "/devices/{device_id}/sync",
    response_model=DDMSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def force_ddm_sync(
    device_id: uuid.UUID,
    db: DBSession,
    _: CurrentUser,
) -> DDMSyncResponse:
    """Force-sync DDM declarations to a device via Jamf Pro."""
    result = await db.execute(
        select(Device).options(selectinload(Device.server)).where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")

    if not device.management_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Device does not have a management_id; DDM may not be enabled on this device.",
        )

    server = device.server
    client_id = decrypt(server.client_id)
    client_secret = decrypt(server.client_secret)
    base_url = server.url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            token = await _get_oauth_token(client, base_url, client_id, client_secret)

            resp = await client.post(
                f"{base_url}/api/v1/ddm/{device.management_id}/sync",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "*/*",
                    "Content-Length": "0",
                },
            )
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cannot reach Jamf Pro server",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Timed out connecting to Jamf Pro",
        )

    if resp.status_code == 403:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Insufficient Jamf Pro API privileges. "
            "Ensure 'Send Declarative Management Command' privilege is granted.",
        )
    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found on Jamf Pro; DDM may not be enabled.",
        )
    if resp.status_code not in (200, 201, 204):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jamf Pro returned {resp.status_code}: {resp.text[:200]}",
        )

    return DDMSyncResponse(
        device_id=device_id,
        management_id=device.management_id,
        message="DDM sync command sent successfully.",
    )
