"""Jamf object migration router.

Supports cross-server migration for policies, smart groups, and static groups.
"""

import logging
import uuid
from copy import deepcopy
from typing import Annotated, Literal
from xml.sax.saxutils import escape as xml_escape

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import ManageMigratorUser
from app.models.server import JamfServer
from app.schemas.migrator import (
    ListMigratorObjectsResponse,
    MigrationDependencyItem,
    MigrationItemResult,
    MigrationPreflightItem,
    MigrationPreflightResponse,
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


def _strip_nonportable_fields_with_id_context(
    obj: object,
    *,
    parent_key: str | None = None,
    keep_id_under: set[str] | None = None,
) -> object:
    """Strip non-portable fields while optionally preserving nested IDs for specific containers."""
    keep_id_under = keep_id_under or set()

    if isinstance(obj, list):
        return [
            _strip_nonportable_fields_with_id_context(
                v, parent_key=parent_key, keep_id_under=keep_id_under
            )
            for v in obj
        ]

    if isinstance(obj, dict):
        blocked = {
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
            if k == "id" and parent_key not in keep_id_under:
                continue
            out[k] = _strip_nonportable_fields_with_id_context(
                v,
                parent_key=k,
                keep_id_under=keep_id_under,
            )
        return out

    return obj


def _collect_policy_dependency_refs(policy_detail: dict) -> tuple[dict[int, str], dict[int, str]]:
    """Collect script and computer-group references from a policy payload."""
    scripts: dict[int, str] = {}
    groups: dict[int, str] = {}

    def _to_int(v: object) -> int | None:
        try:
            return int(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _walk(node: object, parent_key: str | None = None) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item, parent_key=parent_key)
            return

        if isinstance(node, dict):
            if parent_key == "script":
                sid = _to_int(node.get("id"))
                if sid is not None:
                    scripts[sid] = str(node.get("name") or f"Script {sid}")
            if parent_key == "computer_group":
                gid = _to_int(node.get("id"))
                if gid is not None:
                    groups[gid] = str(node.get("name") or f"Group {gid}")

            for k, v in node.items():
                _walk(v, parent_key=k)

    _walk(policy_detail)
    return scripts, groups


def _remap_policy_reference_ids(
    node: object,
    *,
    script_id_map: dict[int, int],
    group_id_map: dict[int, int],
    parent_key: str | None = None,
) -> object:
    """Rewrite policy nested reference IDs from source to target server IDs."""
    if isinstance(node, list):
        return [
            _remap_policy_reference_ids(
                item,
                script_id_map=script_id_map,
                group_id_map=group_id_map,
                parent_key=parent_key,
            )
            for item in node
        ]

    if isinstance(node, dict):
        out: dict = {}
        for k, v in node.items():
            if k == "id" and parent_key in {"script", "computer_group"}:
                try:
                    src_id = int(v)
                except (TypeError, ValueError):
                    out[k] = v
                    continue

                if parent_key == "script":
                    out[k] = script_id_map.get(src_id, src_id)
                else:
                    out[k] = group_id_map.get(src_id, src_id)
                continue

            out[k] = _remap_policy_reference_ids(
                v,
                script_id_map=script_id_map,
                group_id_map=group_id_map,
                parent_key=k,
            )
        return out

    return node


async def _list_target_scripts_by_name(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
) -> dict[str, int]:
    resp = await client.get(
        f"{base_url}/JSSResource/scripts",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to list scripts from target")
    items = _normalize_list_payload(resp.json(), "scripts", "script")
    out: dict[str, int] = {}
    for i in items:
        if i.get("id") and i.get("name"):
            out[str(i["name"])] = int(i["id"])
    return out


async def _list_target_groups_by_name(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
) -> dict[str, int]:
    resp = await client.get(
        f"{base_url}/JSSResource/computergroups",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to list groups from target")
    items = _normalize_list_payload(resp.json(), "computer_groups", "computer_group")
    out: dict[str, int] = {}
    for i in items:
        if i.get("id") and i.get("name"):
            out[str(i["name"])] = int(i["id"])
    return out


async def _migrate_policy_dependencies(
    client: httpx.AsyncClient,
    *,
    source_base_url: str,
    source_token: str,
    target_base_url: str,
    target_token: str,
    policy_detail: dict,
    include_static_members: bool,
    allowed_script_ids: set[int] | None = None,
    allowed_group_ids: set[int] | None = None,
) -> tuple[dict[int, int], dict[int, int], list[str]]:
    """Ensure referenced scripts/groups exist on target and return source->target ID maps."""
    script_refs, group_refs = _collect_policy_dependency_refs(policy_detail)

    target_scripts = await _list_target_scripts_by_name(client, target_base_url, target_token)
    target_groups = await _list_target_groups_by_name(client, target_base_url, target_token)

    missing: list[str] = []

    for src_script_id, script_name in script_refs.items():
        if allowed_script_ids is not None and src_script_id not in allowed_script_ids:
            continue
        if script_name in target_scripts:
            continue

        detail = await _fetch_object_detail(
            client,
            source_base_url,
            source_token,
            "script",
            src_script_id,
        )
        payload = _strip_nonportable_fields(detail)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid script payload for dependency {src_script_id}")

        await _create_on_target(client, target_base_url, target_token, "script", payload)

    for src_group_id, group_name in group_refs.items():
        if allowed_group_ids is not None and src_group_id not in allowed_group_ids:
            continue
        if group_name in target_groups:
            continue

        detail = await _fetch_object_detail(
            client,
            source_base_url,
            source_token,
            "static_group",
            src_group_id,
        )
        payload = _strip_nonportable_fields(detail)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Invalid group payload for dependency {src_group_id}")

        if not _group_is_smart(detail):
            if not include_static_members:
                _clear_static_group_members(payload)
            entity_type: Literal["smart_group", "static_group"] = "static_group"
        else:
            entity_type = "smart_group"

        await _create_on_target(client, target_base_url, target_token, entity_type, payload)

    # Refresh target indexes after creating dependencies.
    target_scripts = await _list_target_scripts_by_name(client, target_base_url, target_token)
    target_groups = await _list_target_groups_by_name(client, target_base_url, target_token)

    script_id_map: dict[int, int] = {}
    group_id_map: dict[int, int] = {}

    for src_script_id, script_name in script_refs.items():
        if allowed_script_ids is not None and src_script_id not in allowed_script_ids:
            continue
        target_id = target_scripts.get(script_name)
        if target_id is None:
            missing.append(f"script:{script_name}")
            continue
        script_id_map[src_script_id] = target_id

    for src_group_id, group_name in group_refs.items():
        if allowed_group_ids is not None and src_group_id not in allowed_group_ids:
            continue
        target_id = target_groups.get(group_name)
        if target_id is None:
            missing.append(f"group:{group_name}")
            continue
        group_id_map[src_group_id] = target_id

    return script_id_map, group_id_map, missing


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
) -> list[str]:
    if entity_type == "policy":
        endpoint = f"{base_url}/JSSResource/policies/id/0"
        bodies = [{"policy": payload}]
    elif entity_type == "script":
        endpoint = f"{base_url}/JSSResource/scripts/id/0"
        bodies = [{"script": payload}]
        if isinstance(payload, dict) and payload.get("category") is not None:
            fallback_payload = deepcopy(payload)
            fallback_payload.pop("category", None)
            bodies.append({"script": fallback_payload})
    else:
        endpoint = f"{base_url}/JSSResource/computergroups/id/0"
        bodies = [{"computer_group": payload}]

    logs: list[str] = []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    # Jamf Classic API behavior can vary by tenant/version.
    # Try endpoint/content variants in order to avoid 415 and category conflicts.
    candidates = [f"{endpoint}?format=json", endpoint]
    last_status = 0
    last_text = ""

    for idx, body in enumerate(bodies):
        if idx > 0 and entity_type == "script":
            logs.append("Retrying script create with category removed")

        json_failed_with_415 = False
        for candidate in candidates:
            logs.append(f"POST {candidate} as JSON")
            resp = await client.post(candidate, headers=headers, json=body)
            if resp.status_code in (200, 201):
                logs.append(f"JSON create succeeded: HTTP {resp.status_code}")
                return logs
            last_status = resp.status_code
            last_text = resp.text[:300]
            logs.append(f"JSON create failed: HTTP {resp.status_code}")
            if resp.status_code != 415:
                break
            json_failed_with_415 = True

        if json_failed_with_415:
            xml_headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/xml",
            }
            root_key = next(iter(body.keys()))
            xml_body = _dict_to_xml(root_key, body[root_key])
            for candidate in candidates:
                logs.append(f"POST {candidate} as XML")
                resp = await client.post(candidate, headers=xml_headers, content=xml_body)
                if resp.status_code in (200, 201):
                    logs.append(f"XML create succeeded: HTTP {resp.status_code}")
                    return logs
                last_status = resp.status_code
                last_text = resp.text[:300]
                logs.append(f"XML create failed: HTTP {resp.status_code}")
                if resp.status_code != 415:
                    break

        # For non-415 failures, try the next body variant (if any) before giving up.
        if idx < len(bodies) - 1:
            continue

    raise RuntimeError(
        f"Target create failed: HTTP {last_status} {last_text}"
    )


def _dict_to_xml(root_name: str, value: object) -> str:
    def _node(name: str, v: object) -> str:
        if isinstance(v, dict):
            inner = "".join(_node(k, x) for k, x in v.items())
            return f"<{name}>{inner}</{name}>"
        if isinstance(v, list):
            singular = name[:-1] if name.endswith("s") and len(name) > 1 else "item"
            inner = "".join(_node(singular, x) for x in v)
            return f"<{name}>{inner}</{name}>"
        if v is None:
            return f"<{name}></{name}>"
        if isinstance(v, bool):
            text = "true" if v else "false"
        else:
            text = str(v)
        return f"<{name}>{xml_escape(text)}</{name}>"

    return '<?xml version="1.0" encoding="UTF-8"?>' + _node(root_name, value)


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


async def _list_target_categories_by_name(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
) -> set[str]:
    resp = await client.get(
        f"{base_url}/JSSResource/categories",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to list categories from target")

    items = _normalize_list_payload(resp.json(), "categories", "category")
    names: set[str] = set()
    for i in items:
        name = i.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


async def _create_category_on_target(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    category_name: str,
) -> None:
    resp = await client.post(
        f"{base_url}/JSSResource/categories/id/0",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={"category": {"name": category_name, "priority": 9}},
    )
    # 409 means already exists (race or concurrent migration)
    if resp.status_code in (200, 201, 409):
        return
    raise RuntimeError(f"Failed to create category '{category_name}' on target: HTTP {resp.status_code}")


def _extract_category_names_from_payload(node: object) -> set[str]:
    """Extract category names from policy/script payloads.

    Handles both string and object category representations.
    """
    names: set[str] = set()

    def _walk(value: object, key: str | None = None) -> None:
        if isinstance(value, dict):
            if key == "category":
                if isinstance(value.get("name"), str) and value.get("name", "").strip():
                    names.add(value["name"].strip())
            for k, v in value.items():
                if k == "category" and isinstance(v, str) and v.strip():
                    names.add(v.strip())
                _walk(v, k)
        elif isinstance(value, list):
            for item in value:
                _walk(item, key)

    _walk(node)
    return names


async def _ensure_payload_categories_exist(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    payload: dict,
) -> list[str]:
    """Ensure any category names referenced in payload exist on target Jamf."""
    category_names = _extract_category_names_from_payload(payload)
    if not category_names:
        return []

    existing = await _list_target_categories_by_name(client, base_url, token)
    created: list[str] = []
    for category_name in sorted(category_names):
        if category_name in existing:
            continue
        await _create_category_on_target(client, base_url, token, category_name)
        created.append(category_name)
        existing.add(category_name)

    return created


def _filter_policy_payload_dependencies(
    node: object,
    *,
    allowed_script_ids: set[int] | None,
    allowed_group_ids: set[int] | None,
    allowed_categories: set[str] | None,
    parent_key: str | None = None,
) -> object | None:
    """Strip unselected policy dependencies from payload so target uses nothing for unchecked items."""
    if isinstance(node, list):
        out: list[object] = []
        for item in node:
            filtered = _filter_policy_payload_dependencies(
                item,
                allowed_script_ids=allowed_script_ids,
                allowed_group_ids=allowed_group_ids,
                allowed_categories=allowed_categories,
                parent_key=parent_key,
            )
            if filtered is not None:
                out.append(filtered)
        return out

    if isinstance(node, dict):
        if parent_key in {"script", "computer_group"}:
            raw_id = node.get("id")
            try:
                dep_id = int(raw_id)
            except (TypeError, ValueError):
                dep_id = None
            # If dependency selection is explicit and this reference has no usable source ID,
            # drop it to avoid unresolved target references (Jamf 409 "Unable to match computer group").
            if parent_key == "script" and allowed_script_ids is not None:
                if dep_id is None or dep_id not in allowed_script_ids:
                    return None
            if parent_key == "computer_group" and allowed_group_ids is not None:
                if dep_id is None or dep_id not in allowed_group_ids:
                    return None

        out: dict = {}
        for k, v in node.items():
            if k == "category":
                if allowed_categories is None:
                    out[k] = v
                elif isinstance(v, str):
                    if v in allowed_categories:
                        out[k] = v
                elif isinstance(v, dict):
                    name = v.get("name")
                    if isinstance(name, str) and name in allowed_categories:
                        out[k] = v
                continue

            filtered = _filter_policy_payload_dependencies(
                v,
                allowed_script_ids=allowed_script_ids,
                allowed_group_ids=allowed_group_ids,
                allowed_categories=allowed_categories,
                parent_key=k,
            )
            if filtered is not None:
                out[k] = filtered
        return out

    return node


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
            item_logs = [f"Begin migration for {body.entity_type} #{object_id}"]
            try:
                detail = await _fetch_object_detail(
                    client,
                    source.url.rstrip("/"),
                    source_token,
                    body.entity_type,
                    object_id,
                )
                name = detail.get("name") or f"Object {object_id}"
                item_logs.append(f"Fetched source object: {name}")

                if body.skip_existing and name in existing_names:
                    skipped += 1
                    item_logs.append("Skipped because object with same name exists on target")
                    results.append(
                        MigrationItemResult(
                            object_id=object_id,
                            name=name,
                            status="skipped",
                            message="Already exists on target",
                            logs=item_logs,
                        )
                    )
                    continue

                payload = _strip_nonportable_fields(detail)
                if not isinstance(payload, dict):
                    raise RuntimeError("Invalid payload received from source")

                if body.entity_type == "policy":
                    script_refs, group_refs = _collect_policy_dependency_refs(detail)
                    category_refs = _extract_category_names_from_payload(detail)

                    allowed_script_ids = (
                        set(body.selected_dependency_script_ids)
                        if body.selected_dependency_script_ids is not None
                        else set(script_refs.keys())
                    )
                    allowed_group_ids = (
                        set(body.selected_dependency_group_ids)
                        if body.selected_dependency_group_ids is not None
                        else set(group_refs.keys())
                    )
                    allowed_categories = (
                        set(body.selected_dependency_categories)
                        if body.selected_dependency_categories is not None
                        else set(category_refs)
                    )

                    script_id_map: dict[int, int] = {}
                    group_id_map: dict[int, int] = {}

                    if body.migrate_dependencies:
                        item_logs.append("Resolving and migrating policy dependencies")
                        script_id_map, group_id_map, missing = await _migrate_policy_dependencies(
                            client,
                            source_base_url=source.url.rstrip("/"),
                            source_token=source_token,
                            target_base_url=target.url.rstrip("/"),
                            target_token=target_token,
                            policy_detail=detail,
                            include_static_members=body.include_static_members,
                            allowed_script_ids=allowed_script_ids,
                            allowed_group_ids=allowed_group_ids,
                        )
                        if missing:
                            raise RuntimeError(
                                "Missing dependencies on target after migration: " + ", ".join(missing)
                            )
                        item_logs.append(
                            f"Dependencies ready: scripts={len(script_id_map)} groups={len(group_id_map)}"
                        )

                    # Preserve and remap script/group reference IDs inside policy payload.
                    payload = _strip_nonportable_fields_with_id_context(
                        detail,
                        keep_id_under={"script", "computer_group"},
                    )
                    if not isinstance(payload, dict):
                        raise RuntimeError("Invalid policy payload after sanitization")

                    filtered_payload = _filter_policy_payload_dependencies(
                        payload,
                        allowed_script_ids=allowed_script_ids,
                        allowed_group_ids=allowed_group_ids,
                        allowed_categories=allowed_categories,
                    )
                    if not isinstance(filtered_payload, dict):
                        raise RuntimeError("Invalid policy payload after dependency filtering")
                    payload = filtered_payload

                    payload = _remap_policy_reference_ids(
                        payload,
                        script_id_map=script_id_map,
                        group_id_map=group_id_map,
                    )

                # Static groups should not carry member IDs across servers by default.
                if body.entity_type == "static_group" and not body.include_static_members:
                    _clear_static_group_members(payload)
                    item_logs.append("Cleared static group members for safe cross-server create")

                if body.entity_type in {"policy", "script"}:
                    created_categories = await _ensure_payload_categories_exist(
                        client,
                        target.url.rstrip("/"),
                        target_token,
                        payload,
                    )
                    if created_categories:
                        item_logs.append(
                            "Created missing target categories: " + ", ".join(created_categories)
                        )

                try:
                    create_logs = await _create_on_target(
                        client,
                        target.url.rstrip("/"),
                        target_token,
                        body.entity_type,
                        payload,
                    )
                except RuntimeError as exc:
                    err = str(exc)
                    if (
                        body.entity_type in {"policy", "script"}
                        and "No match found for category" in err
                    ):
                        item_logs.append("Retrying without category because target category reference is invalid")
                        payload_no_category = deepcopy(payload)
                        if isinstance(payload_no_category, dict):
                            if "category" in payload_no_category:
                                payload_no_category.pop("category", None)
                            general = payload_no_category.get("general")
                            if isinstance(general, dict):
                                general.pop("category", None)
                        create_logs = await _create_on_target(
                            client,
                            target.url.rstrip("/"),
                            target_token,
                            body.entity_type,
                            payload_no_category,
                        )
                    else:
                        raise
                item_logs.extend(create_logs)
                created += 1
                existing_names.add(name)
                item_logs.append("Migration created successfully")
                results.append(
                    MigrationItemResult(
                        object_id=object_id,
                        name=name,
                        status="created",
                        logs=item_logs,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                item_logs.append(f"Failure: {exc}")
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
                        logs=item_logs,
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


@router.post("/preflight", response_model=MigrationPreflightResponse)
async def preflight_migration(
    body: MigrationRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: ManageMigratorUser,
) -> MigrationPreflightResponse:
    """Preview migration dependencies so UI can present checkbox selections before migrate."""
    source = await _load_server(db, body.source_server_id)
    target = await _load_server(db, body.target_server_id)

    if body.entity_type != "policy":
        items = [
            MigrationPreflightItem(
                object_id=object_id,
                name=f"Object {object_id}",
                dependencies=[],
            )
            for object_id in body.object_ids
        ]
        return MigrationPreflightResponse(
            entity_type=body.entity_type,
            source_server_id=body.source_server_id,
            target_server_id=body.target_server_id,
            items=items,
        )

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

        target_scripts = await _list_target_scripts_by_name(client, target.url.rstrip("/"), target_token)
        target_groups = await _list_target_groups_by_name(client, target.url.rstrip("/"), target_token)
        target_categories = await _list_target_categories_by_name(client, target.url.rstrip("/"), target_token)

        items: list[MigrationPreflightItem] = []
        for object_id in body.object_ids:
            detail = await _fetch_object_detail(
                client,
                source.url.rstrip("/"),
                source_token,
                "policy",
                object_id,
            )
            name = str(detail.get("name") or f"Object {object_id}")
            script_refs, group_refs = _collect_policy_dependency_refs(detail)
            category_refs = _extract_category_names_from_payload(detail)

            deps: list[MigrationDependencyItem] = []
            for sid, sname in script_refs.items():
                if sname not in target_scripts:
                    deps.append(MigrationDependencyItem(dependency_type="script", id=sid, name=sname))
            for gid, gname in group_refs.items():
                if gname not in target_groups:
                    deps.append(MigrationDependencyItem(dependency_type="group", id=gid, name=gname))
            for cname in sorted(category_refs):
                if cname not in target_categories:
                    deps.append(MigrationDependencyItem(dependency_type="category", name=cname))

            items.append(MigrationPreflightItem(object_id=object_id, name=name, dependencies=deps))

    return MigrationPreflightResponse(
        entity_type=body.entity_type,
        source_server_id=body.source_server_id,
        target_server_id=body.target_server_id,
        items=items,
    )
