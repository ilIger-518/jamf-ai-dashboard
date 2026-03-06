"""Jamf server management router (admin only)."""

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.dependencies import AdminUser, CurrentUser, DBSession
from app.models.server import JamfServer
from app.schemas.servers import ServerCreate, ServerResponse, ServerUpdate
from app.services.encryption import decrypt, encrypt

router = APIRouter(prefix="/servers", tags=["servers"])


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
