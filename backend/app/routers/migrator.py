"""Jamf object migration router.

Supports cross-server migration for policies, smart groups, and static groups.
"""

import logging
import uuid
from typing import Literal
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import ManageMigratorUser
from app.models.server import JamfServer
from app.schemas.migrator import (
    ListMigratorObjectsResponse,
    MigrationItemResult,
    MigrationRequest,
    MigrationResponse,
    MigratorObject,
)
from app.services.encryption import decrypt

router = APIRouter(prefix="/migrator", tags=["migrator"])
logger = logging.getLogger(__name__)


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


async def _load_server(db: AsyncSession, server_id: uuid.UUID) -> JamfServer:
    result = await db.execute(select(JamfServer).where(JamfServer.id == server_id))
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Server not found")
    return server


def _group_is_smart(group: dict) -> bool:
    raw = group.get("is_smart")
    if raw is None:
        raw = group.get("isSmart")
    if raw is None:
        raw = group.get("is_smart_group")

    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"true", "1", "yes"}
    if isinstance(raw, (int, float)):
        return raw != 0
    return False


def _normalize_list_payload(raw: dict, root_key: str, item_key: str) -> list[dict]:
    """Jamf Classic list endpoints are inconsistent; normalize into a list."""
    val = raw.get(root_key) or []
    if isinstance(val, dict):
        items = val.get(item_key) or []
        if isinstance(items, dict):
            return [items]
        return items
    return val


async def _list_source_objects(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    entity_type: str,
) -> list[MigratorObject]:
    if entity_type == "policy":
        resp = await client.get(
            f"{base_url}/JSSResource/policies",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to list policies from source")
        items = _normalize_list_payload(resp.json(), "policies", "policy")
        return [
            MigratorObject(id=int(i["id"]), name=i.get("name") or f"Policy {i['id']}", entity_type="policy")
            for i in items
            if i.get("id")
        ]

    if entity_type == "script":
        resp = await client.get(
            f"{base_url}/JSSResource/scripts",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to list scripts from source")
        items = _normalize_list_payload(resp.json(), "scripts", "script")
        return [
            MigratorObject(id=int(i["id"]), name=i.get("name") or f"Script {i['id']}", entity_type="script")
            for i in items
            if i.get("id")
        ]

    resp = await client.get(
        f"{base_url}/JSSResource/computergroups",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to list computer groups from source")

    groups = _normalize_list_payload(resp.json(), "computer_groups", "computer_group")

    if entity_type == "smart_group":
        groups = [g for g in groups if _group_is_smart(g)]
    else:
        groups = [g for g in groups if not _group_is_smart(g)]

    return [
        MigratorObject(
            id=int(g["id"]),
            name=g.get("name") or f"Group {g['id']}",
            entity_type=entity_type,
        )
        for g in groups
        if g.get("id")
    ]


def _strip_nonportable_fields(obj: object) -> object:
    """Remove identifiers and metadata keys that should never be posted to target."""
    if isinstance(obj, list):
        return [_strip_nonportable_fields(v) for v in obj]
    if isinstance(obj, dict):
        blocked = {
            "id",
            "uuid",
            "href",
            "link",
            "links",
            "uri",
            "version_lock",
            "self_service_icon_id",
        }
        out: dict = {}
        for k, v in obj.items():
            if k in blocked:
                continue
            out[k] = _strip_nonportable_fields(v)
        return out
    return obj


async def _target_names(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    entity_type: str,
) -> set[str]:
    items = await _list_source_objects(client, base_url, token, entity_type)
    return {i.name for i in items}


async def _fetch_object_detail(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    entity_type: str,
    object_id: int,
) -> dict:
    if entity_type == "policy":
        resp = await client.get(
            f"{base_url}/JSSResource/policies/id/{object_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch policy {object_id}: HTTP {resp.status_code}")
        return resp.json().get("policy") or {}

    if entity_type == "script":
        resp = await client.get(
            f"{base_url}/JSSResource/scripts/id/{object_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch script {object_id}: HTTP {resp.status_code}")
        return resp.json().get("script") or {}

    resp = await client.get(
        f"{base_url}/JSSResource/computergroups/id/{object_id}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch group {object_id}: HTTP {resp.status_code}")
    return resp.json().get("computer_group") or {}


async def _create_on_target(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    entity_type: str,
    payload: dict,
) -> None:
    if entity_type == "policy":
        endpoint = f"{base_url}/JSSResource/policies/id/0"
        body = {"policy": payload}
    elif entity_type == "script":
        endpoint = f"{base_url}/JSSResource/scripts/id/0"
        body = {"script": payload}
    else:
        endpoint = f"{base_url}/JSSResource/computergroups/id/0"
        body = {"computer_group": payload}

    resp = await client.post(
        endpoint,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        json=body,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Target create failed: HTTP {resp.status_code} {resp.text[:200]}")


def _clear_static_group_members(payload: dict) -> None:
    """Normalize static group members to empty for safe cross-server creation."""
    computers = payload.get("computers")
    if isinstance(computers, dict):
        if "computer" in computers:
            computers["computer"] = []
        else:
            payload["computers"] = {"computer": []}
        return

    payload["computers"] = {"computer": []}


@router.get("/objects", response_model=ListMigratorObjectsResponse)
async def list_objects(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: ManageMigratorUser,
    source_server_id: uuid.UUID = Query(...),
    entity_type: Literal["policy", "smart_group", "static_group", "script"] = Query(...),
) -> ListMigratorObjectsResponse:
    source = await _load_server(db, source_server_id)

    async with httpx.AsyncClient(timeout=45) as client:
        token = await _get_oauth_token(
            client,
            source.url.rstrip("/"),
            decrypt(source.client_id),
            decrypt(source.client_secret),
        )
        items = await _list_source_objects(client, source.url.rstrip("/"), token, entity_type)
    logger.info(
        "Loaded migrator objects",
        extra={
            "source_server_id": str(source_server_id),
            "entity_type": entity_type,
            "count": len(items),
        },
    )

    items.sort(key=lambda x: x.name.lower())
    return ListMigratorObjectsResponse(items=items)


@router.post("/migrate", response_model=MigrationResponse)
async def migrate_objects(
    body: MigrationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: ManageMigratorUser,
) -> MigrationResponse:
    source = await _load_server(db, body.source_server_id)
    target = await _load_server(db, body.target_server_id)

    async with httpx.AsyncClient(timeout=60) as client:
        source_token = await _get_oauth_token(
            client,
            source.url.rstrip("/"),
            decrypt(source.client_id),
            decrypt(source.client_secret),
        )
        target_token = await _get_oauth_token(
            client,
            target.url.rstrip("/"),
            decrypt(target.client_id),
            decrypt(target.client_secret),
        )

        existing_names = await _target_names(
            client,
            target.url.rstrip("/"),
            target_token,
            body.entity_type,
        )

        results: list[MigrationItemResult] = []
        created = skipped = failed = 0

        for object_id in body.object_ids:
            try:
                detail = await _fetch_object_detail(
                    client,
                    source.url.rstrip("/"),
                    source_token,
                    body.entity_type,
                    object_id,
                )
                name = detail.get("name") or f"Object {object_id}"

                if body.skip_existing and name in existing_names:
                    skipped += 1
                    results.append(
                        MigrationItemResult(
                            object_id=object_id,
                            name=name,
                            status="skipped",
                            message="Already exists on target",
                        )
                    )
                    continue

                payload = _strip_nonportable_fields(detail)
                if not isinstance(payload, dict):
                    raise RuntimeError("Invalid payload received from source")

                # Static groups should not carry member IDs across servers by default.
                if body.entity_type == "static_group" and not body.include_static_members:
                    _clear_static_group_members(payload)

                await _create_on_target(
                    client,
                    target.url.rstrip("/"),
                    target_token,
                    body.entity_type,
                    payload,
                )
                created += 1
                existing_names.add(name)
                results.append(
                    MigrationItemResult(
                        object_id=object_id,
                        name=name,
                        status="created",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.warning(
                    "Migrator item failed",
                    extra={
                        "entity_type": body.entity_type,
                        "object_id": object_id,
                        "source_server_id": str(body.source_server_id),
                        "target_server_id": str(body.target_server_id),
                        "error": str(exc),
                    },
                )
                results.append(
                    MigrationItemResult(
                        object_id=object_id,
                        name=f"Object {object_id}",
                        status="failed",
                        message=str(exc),
                    )
                )

    return MigrationResponse(
        entity_type=body.entity_type,
        source_server_id=body.source_server_id,
        target_server_id=body.target_server_id,
        created=created,
        skipped=skipped,
        failed=failed,
        results=results,
    )
