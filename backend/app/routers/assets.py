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
from app.schemas.assets import PackageItem, ScriptDetailItem, ScriptItem, ScriptParameter
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


def _extract_category_name(raw_category: object) -> str | None:
    if isinstance(raw_category, dict):
        return raw_category.get("name")
    if isinstance(raw_category, str):
        return raw_category
    return None


def _jamf_script_url(base_url: str, script_id: int) -> str:
    return (
        f"{base_url.rstrip('/')}/view/settings/computer-management/scripts/{script_id}?tab=general"
    )


def _extract_script_parameters(payload: dict) -> list[ScriptParameter]:
    out: list[ScriptParameter] = []
    for idx in range(4, 12):
        value = payload.get(f"parameter{idx}")
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized:
            continue
        out.append(
            ScriptParameter(index=idx, label=f"Parameter {idx}", value=normalized)
        )
    return out


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
            category=_extract_category_name(i.get("category")),
            jamf_script_url=_jamf_script_url(server.url, int(i["id"])),
        )
        for i in raw_items
        if i.get("id")
    ]
    out.sort(key=lambda x: x.name.lower())
    return out


@router.get("/scripts/{script_id}", response_model=ScriptDetailItem)
async def get_script_detail(
    script_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: CurrentUser,
    server_id: uuid.UUID = Query(...),
) -> ScriptDetailItem:
    server = await _load_server(db, server_id)

    async with httpx.AsyncClient(timeout=45) as client:
        token = await _get_oauth_token(
            client,
            server.url.rstrip("/"),
            decrypt(server.client_id),
            decrypt(server.client_secret),
        )
        resp = await client.get(
            f"{server.url.rstrip('/')}/JSSResource/scripts/id/{script_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to load script {script_id}: HTTP {resp.status_code}",
            )

    raw_script = (resp.json() or {}).get("script") or {}
    name = raw_script.get("name") or f"Script {script_id}"
    return ScriptDetailItem(
        id=script_id,
        name=name,
        category=_extract_category_name(raw_script.get("category")),
        notes=raw_script.get("notes"),
        info=raw_script.get("info"),
        priority=raw_script.get("priority"),
        os_requirements=raw_script.get("os_requirements"),
        script_contents=str(raw_script.get("script_contents") or ""),
        parameters=_extract_script_parameters(raw_script),
        jamf_script_url=_jamf_script_url(server.url, script_id),
    )


@router.get("/packages", response_model=list[PackageItem])
async def list_packages(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: CurrentUser,
    server_id: uuid.UUID = Query(...),
) -> list[PackageItem]:
    server = await _load_server(db, server_id)

    async with httpx.AsyncClient(timeout=45) as client:
        credential_sets: list[tuple[str, str, str]] = [
            (
                "primary",
                decrypt(server.client_id),
                decrypt(server.client_secret),
            )
        ]
        if server.ai_client_id and server.ai_client_secret:
            credential_sets.append(
                (
                    "ai",
                    decrypt(server.ai_client_id),
                    decrypt(server.ai_client_secret),
                )
            )

        raw_items: list[dict] = []
        failures: list[str] = []
        package_endpoints = [
            ("/api/v1/packages", {"page": 0, "page-size": 200}, "modern"),
            ("/JSSResource/packages", None, "classic"),
            ("/JSSResource/packages/subset/basic", None, "classic-subset"),
        ]

        for credential_label, client_id, client_secret in credential_sets:
            try:
                token = await _get_oauth_token(
                    client,
                    server.url.rstrip("/"),
                    client_id,
                    client_secret,
                )
            except HTTPException as exc:
                failures.append(f"{credential_label}:oauth:{exc.detail}")
                continue

            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            for endpoint, params, label in package_endpoints:
                resp = await client.get(
                    f"{server.url.rstrip('/')}{endpoint}",
                    headers=headers,
                    params=params,
                )
                if resp.status_code != 200:
                    failures.append(f"{credential_label}:{label}:{resp.status_code}")
                    continue

                payload = resp.json()
                if endpoint.startswith("/api/"):
                    if isinstance(payload, dict):
                        raw_items = payload.get("results") or payload.get("packages") or []
                    elif isinstance(payload, list):
                        raw_items = payload
                else:
                    raw_items = _normalize_list_payload(payload, "packages", "package")

                if raw_items:
                    break

            if raw_items:
                break

        if not raw_items and failures:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list packages ({', '.join(failures)})",
            )

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
