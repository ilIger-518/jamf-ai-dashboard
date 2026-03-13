"""Live Jamf assets router for scripts and packages."""

import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser
from app.models.server import JamfServer
from app.schemas.assets import PackageItem, ScriptItem
from app.services.encryption import decrypt

router = APIRouter(prefix="/assets", tags=["assets"])


def _normalize_list_payload(raw: dict, root_key: str, item_key: str) -> list[dict]:
    val = raw.get(root_key) or []
    if isinstance(val, dict):
        items = val.get(item_key) or []
        if isinstance(items, dict):
            return [items]
        return items
    return val


async def _load_server(db: AsyncSession, server_id: uuid.UUID) -> JamfServer:
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return server


async def _get_oauth_token(
    client: httpx.AsyncClient, base_url: str, client_id: str, client_secret: str
) -> str:
    resp = await client.post(
        f"{base_url}/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OAuth failed for {base_url}: {resp.status_code}",
        )
    return resp.json()["access_token"]


@router.get("/scripts", response_model=list[ScriptItem])
async def list_scripts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: CurrentUser,
    server_id: uuid.UUID = Query(...),
) -> list[ScriptItem]:
    server = await _load_server(db, server_id)

    async with httpx.AsyncClient(timeout=45) as client:
        token = await _get_oauth_token(
            client,
            server.url.rstrip("/"),
            decrypt(server.client_id),
            decrypt(server.client_secret),
        )
        resp = await client.get(
            f"{server.url.rstrip('/')}/JSSResource/scripts",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list scripts: HTTP {resp.status_code}",
            )

    raw_items = _normalize_list_payload(resp.json(), "scripts", "script")
    out = [
        ScriptItem(
            id=int(i["id"]),
            name=i.get("name") or f"Script {i['id']}",
            category=(i.get("category") or {}).get("name") if isinstance(i.get("category"), dict) else i.get("category"),
        )
        for i in raw_items
        if i.get("id")
    ]
    out.sort(key=lambda x: x.name.lower())
    return out


@router.get("/packages", response_model=list[PackageItem])
async def list_packages(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: CurrentUser,
    server_id: uuid.UUID = Query(...),
) -> list[PackageItem]:
    server = await _load_server(db, server_id)

    async with httpx.AsyncClient(timeout=45) as client:
        token = await _get_oauth_token(
            client,
            server.url.rstrip("/"),
            decrypt(server.client_id),
            decrypt(server.client_secret),
        )
        resp = await client.get(
            f"{server.url.rstrip('/')}/JSSResource/packages",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list packages: HTTP {resp.status_code}",
            )

    raw_items = _normalize_list_payload(resp.json(), "packages", "package")
    out = [
        PackageItem(
            id=int(i["id"]),
            name=i.get("name") or f"Package {i['id']}",
            filename=i.get("filename") or i.get("file_name"),
            category=(i.get("category") or {}).get("name") if isinstance(i.get("category"), dict) else i.get("category"),
        )
        for i in raw_items
        if i.get("id")
    ]
    out.sort(key=lambda x: x.name.lower())
    return out
