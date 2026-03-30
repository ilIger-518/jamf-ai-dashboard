"""Jamf server management router (admin only)."""

import asyncio
import uuid

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import CurrentUser, DBSession, ManageServersUser, ManageServerSyncUser
from app.models.server import JamfServer
from app.schemas.servers import (
    FULL_PRIVILEGES,
    READONLY_PRIVILEGES,
    ProvisionResult,
    ServerCreate,
    ServerProvision,
    ServerResponse,
    ServerUpdate,
)
from app.services.encryption import encrypt
from app.services.jamf.sync import get_sync_result, get_sync_status, sync_all_servers, sync_server

router = APIRouter(prefix="/servers", tags=["servers"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADMIN_ROLE_NAME = "Jamf AI Dashboard - Admin"
_READONLY_ROLE_NAME = "Jamf AI Dashboard - Read Only"
_ADMIN_CLIENT_NAME = "Jamf AI Dashboard - Admin Client"
_READONLY_CLIENT_NAME = "Jamf AI Dashboard - Read-Only Client"
_TOKEN_LIFETIME = 1800  # seconds


async def _jamf_bearer_token(
    client: httpx.AsyncClient, base_url: str, username: str, password: str
) -> str:
    """Obtain a Jamf Pro bearer token via Basic-auth credentials."""
    resp = await client.post(
        f"{base_url}/api/v1/auth/token",
        auth=(username, password),
    )
    if resp.status_code == 401:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid Jamf Pro credentials"
        )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Jamf Pro token endpoint returned {resp.status_code}",
        )
    return resp.json()["token"]


async def _create_role(
    client: httpx.AsyncClient, base_url: str, token: str, display_name: str, privileges: list[str]
) -> None:
    """Create an API role.  Silently skips if the role already exists
    (Jamf Pro returns 409 *or* 400 "must be unique" for duplicates)."""
    resp = await client.post(
        f"{base_url}/api/v1/api-roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"displayName": display_name, "privileges": privileges},
    )
    if resp.status_code in (200, 201, 409):
        return
    # Jamf Pro 11+ returns 400 with "must be unique" instead of 409
    if resp.status_code == 400 and "must be unique" in resp.text:
        return
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Failed to create API role '{display_name}': {resp.status_code} {resp.text[:200]}",
    )


async def _create_client(
    client: httpx.AsyncClient, base_url: str, token: str, display_name: str, role_name: str
) -> tuple[str, str]:
    """Create an API integration and generate its client secret.
    Returns (client_id, client_secret).
    """
    headers = {"Authorization": f"Bearer {token}"}
    # Create integration
    resp = await client.post(
        f"{base_url}/api/v1/api-integrations",
        headers=headers,
        json={
            "authorizationScopes": [role_name],
            "displayName": display_name,
            "enabled": True,
            "accessTokenLifetimeSeconds": _TOKEN_LIFETIME,
        },
    )
    if resp.status_code not in (200, 201):
        # Jamf Pro returns 400 "must be unique" for duplicate display names
        if resp.status_code == 400 and "must be unique" in resp.text:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An API integration named '{display_name}' already exists in Jamf Pro. "
                f"Delete it first or use the existing credentials.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create API integration '{display_name}': {resp.status_code} {resp.text[:200]}",
        )
    integration_id = resp.json()["id"]

    # Generate client secret
    cred_resp = await client.post(
        f"{base_url}/api/v1/api-integrations/{integration_id}/client-credentials",
        headers=headers,
    )
    if cred_resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate client credentials: {cred_resp.status_code} {cred_resp.text[:200]}",
        )
    creds = cred_resp.json()
    return creds["clientId"], creds["clientSecret"]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ServerResponse])
async def list_servers(db: DBSession, _: CurrentUser) -> list[ServerResponse]:
    result = await db.execute(select(JamfServer).order_by(JamfServer.name))
    return [ServerResponse.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=ServerResponse, status_code=status.HTTP_201_CREATED)
async def create_server(body: ServerCreate, db: DBSession, _: ManageServersUser) -> ServerResponse:
    server = JamfServer(
        name=body.name,
        url=body.url.rstrip("/"),
        client_id=encrypt(body.client_id),
        client_secret=encrypt(body.client_secret),
        ai_client_id=encrypt(body.ai_client_id) if body.ai_client_id else None,
        ai_client_secret=encrypt(body.ai_client_secret) if body.ai_client_secret else None,
    )
    db.add(server)
    await db.flush()
    await db.refresh(server)
    return ServerResponse.model_validate(server)


@router.patch("/{server_id}", response_model=ServerResponse)
async def update_server(
    server_id: uuid.UUID, body: ServerUpdate, db: DBSession, _: ManageServersUser
) -> ServerResponse:
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")

    if body.name is not None:
        server.name = body.name
    if body.url is not None:
        server.url = body.url.rstrip("/")
    if body.client_id is not None:
        server.client_id = encrypt(body.client_id)
    if body.client_secret is not None:
        server.client_secret = encrypt(body.client_secret)
    if body.ai_client_id is not None:
        server.ai_client_id = encrypt(body.ai_client_id)
    if body.ai_client_secret is not None:
        server.ai_client_secret = encrypt(body.ai_client_secret)
    if body.is_active is not None:
        server.is_active = body.is_active

    await db.flush()
    await db.refresh(server)
    return ServerResponse.model_validate(server)


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(server_id: uuid.UUID, db: DBSession, _: ManageServersUser) -> None:
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    await db.delete(server)


@router.post("/provision", response_model=ProvisionResult, status_code=status.HTTP_201_CREATED)
async def provision_server(
    body: ServerProvision, db: DBSession, _: ManageServersUser
) -> ProvisionResult:
    """Auto-provision a Jamf Pro server.

    Uses the supplied admin credentials to:
    1. Obtain a short-lived bearer token from Jamf Pro.
    2. Create a read-only API role + client (used by the AI module).
    3. Create a full-access API role + client (used for data sync).
    4. Save the server record with Fernet-encrypted credentials.

    The admin username/password are used only during this call and are never stored.
    """
    base_url = body.jamf_url.rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await _jamf_bearer_token(client, base_url, body.username, body.password)

            # Always create the read-only role + client
            await _create_role(client, base_url, token, _READONLY_ROLE_NAME, READONLY_PRIVILEGES)
            ro_id, ro_secret = await _create_client(
                client, base_url, token, _READONLY_CLIENT_NAME, _READONLY_ROLE_NAME
            )

            # Only create the admin role + client for the "full" preset
            if body.preset == "full":
                await _create_role(client, base_url, token, _ADMIN_ROLE_NAME, FULL_PRIVILEGES)
                adm_id, adm_secret = await _create_client(
                    client, base_url, token, _ADMIN_CLIENT_NAME, _ADMIN_ROLE_NAME
                )
            else:
                # Read-only preset: use the same credentials for both slots
                adm_id, adm_secret = ro_id, ro_secret

    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cannot reach Jamf Pro server — check the URL",
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="Timed out connecting to Jamf Pro"
        )

    # Persist to DB
    server = JamfServer(
        name=body.server_name,
        url=base_url,
        client_id=encrypt(adm_id),
        client_secret=encrypt(adm_secret),
        ai_client_id=encrypt(ro_id),
        ai_client_secret=encrypt(ro_secret),
    )
    db.add(server)
    await db.flush()
    await db.refresh(server)

    return ProvisionResult(
        server=ServerResponse.model_validate(server),
        admin_role=_ADMIN_ROLE_NAME if body.preset == "full" else "",
        admin_client_display_name=_ADMIN_CLIENT_NAME if body.preset == "full" else "",
        readonly_role=_READONLY_ROLE_NAME,
        readonly_client_display_name=_READONLY_CLIENT_NAME,
    )


# ---------------------------------------------------------------------------
# Manual sync endpoints
# ---------------------------------------------------------------------------


@router.post("/{server_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(server_id: uuid.UUID, db: DBSession, _: ManageServerSyncUser) -> dict:
    """Kick off a background sync for a specific server."""
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")

    asyncio.create_task(sync_server(str(server_id)))
    return {"status": "started", "server_id": str(server_id)}


@router.post("/sync-all", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync_all(_: ManageServerSyncUser) -> dict:
    """Kick off a background sync for all active servers."""
    asyncio.create_task(sync_all_servers())
    return {"status": "started"}


@router.get("/{server_id}/sync/status")
async def get_server_sync_status(server_id: uuid.UUID, db: DBSession, _: CurrentUser) -> dict:
    """Return the current sync status for a server (running / idle / error)."""
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")

    sync_status = await get_sync_status(str(server_id))
    last_result = await get_sync_result(str(server_id))
    return {
        "server_id": str(server_id),
        "status": sync_status,
        "last_sync": server.last_sync.isoformat() if server.last_sync else None,
        "last_sync_error": server.last_sync_error,
        "last_sync_result": last_result,
    }


@router.get("/sync/statuses")
async def get_all_server_sync_statuses(db: DBSession, _: CurrentUser) -> list[dict]:
    """Return sync status and last summary payload for all servers."""
    result = await db.execute(select(JamfServer).order_by(JamfServer.name))
    servers = result.scalars().all()

    rows: list[dict] = []
    for server in servers:
        server_id = str(server.id)
        rows.append(
            {
                "server_id": server_id,
                "status": await get_sync_status(server_id),
                "last_sync": server.last_sync.isoformat() if server.last_sync else None,
                "last_sync_error": server.last_sync_error,
                "last_sync_result": await get_sync_result(server_id),
            }
        )
    return rows
