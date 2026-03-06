"""Jamf server management router (admin only)."""

import uuid

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import AdminUser, CurrentUser, DBSession
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
    """Create an API role (ignore 409 Conflict — role already exists)."""
    resp = await client.post(
        f"{base_url}/api/v1/api-roles",
        headers={"Authorization": f"Bearer {token}"},
        json={"displayName": display_name, "privileges": privileges},
    )
    if resp.status_code not in (200, 201, 409):
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
async def create_server(body: ServerCreate, db: DBSession, _: AdminUser) -> ServerResponse:
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
    server_id: uuid.UUID, body: ServerUpdate, db: DBSession, _: AdminUser
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
async def delete_server(server_id: uuid.UUID, db: DBSession, _: AdminUser) -> None:
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    await db.delete(server)


@router.post("/provision", response_model=ProvisionResult, status_code=status.HTTP_201_CREATED)
async def provision_server(body: ServerProvision, db: DBSession, _: AdminUser) -> ProvisionResult:
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

            # Create both roles (ignore if already exist)
            await _create_role(client, base_url, token, _READONLY_ROLE_NAME, READONLY_PRIVILEGES)
            await _create_role(client, base_url, token, _ADMIN_ROLE_NAME, FULL_PRIVILEGES)

            # Create clients and generate secrets
            ro_id, ro_secret = await _create_client(
                client, base_url, token, _READONLY_CLIENT_NAME, _READONLY_ROLE_NAME
            )
            adm_id, adm_secret = await _create_client(
                client, base_url, token, _ADMIN_CLIENT_NAME, _ADMIN_ROLE_NAME
            )

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
        admin_role=_ADMIN_ROLE_NAME,
        admin_client_display_name=_ADMIN_CLIENT_NAME,
        readonly_role=_READONLY_ROLE_NAME,
        readonly_client_display_name=_READONLY_CLIENT_NAME,
    )
