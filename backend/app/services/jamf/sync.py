"""Jamf Pro sync service.

Fetches computers from a Jamf Pro instance and upserts them into the local DB.

Endpoint priority (tried in order until one succeeds):
  1. GET /api/v2/computers          — Jamf Pro 10.49+ (nested JSON, rich data)
  2. GET /api/v1/computers-preview  — Jamf Pro 10.32–10.48 (flat JSON)
  3. GET /JSSResource/computers     — Classic API, all versions (basic fields)

OAuth:  POST /api/oauth/token  (client_credentials grant)
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import delete, select

from app.cache import get_redis
from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.patch import PatchTitle
from app.models.policy import Policy
from app.models.server import JamfServer
from app.models.smart_group import SmartGroup
from app.services.encryption import decrypt

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200
_SYNC_STATUS_TTL = 3600  # Redis key TTL in seconds


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


def _redis_key(server_id: str) -> str:
    return f"sync:status:{server_id}"


def _redis_result_key(server_id: str) -> str:
    return f"sync:last_result:{server_id}"


async def get_sync_status(server_id: str) -> str:
    """Return 'running', 'idle', or 'error' from Redis (default: 'idle')."""
    redis = await get_redis()
    val = await redis.get(_redis_key(server_id))
    if val is None:
        return "idle"
    if isinstance(val, bytes):
        return val.decode()
    return str(val)


async def _set_status(server_id: str, status: str) -> None:
    redis = await get_redis()
    await redis.set(_redis_key(server_id), status, ex=_SYNC_STATUS_TTL)


async def get_sync_result(server_id: str) -> dict | None:
    """Return the latest sync summary payload from Redis, if available."""
    redis = await get_redis()
    val = await redis.get(_redis_result_key(server_id))
    if val is None:
        return None
    raw = val.decode() if isinstance(val, bytes) else str(val)
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except Exception:  # noqa: BLE001
        return None


async def _set_sync_result(server_id: str, payload: dict) -> None:
    redis = await get_redis()
    await redis.set(_redis_result_key(server_id), json.dumps(payload), ex=_SYNC_STATUS_TTL)


# ---------------------------------------------------------------------------
# OAuth token
# ---------------------------------------------------------------------------


async def _get_oauth_token(
    client: httpx.AsyncClient, base_url: str, client_id: str, client_secret: str
) -> str:
    """Obtain a short-lived bearer token via client_credentials grant."""
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
        raise RuntimeError(f"Jamf Pro OAuth failed ({resp.status_code}): {resp.text[:200]}")
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Computer upsert helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _upsert_device(db_session, server_id, jamf_id: int, fields: dict) -> str:
    existing = await db_session.execute(
        select(Device).where(Device.jamf_id == jamf_id, Device.server_id == server_id)
    )
    devices = existing.scalars().all()
    action = "updated"
    if not devices:
        device = Device(jamf_id=jamf_id, server_id=server_id)
        db_session.add(device)
        action = "created"
    else:
        device = devices[0]
        for dup in devices[1:]:
            await db_session.delete(dup)

    for attr, value in fields.items():
        setattr(device, attr, value)
    device.synced_at = datetime.now(UTC)
    return action


async def _purge_missing_by_jamf_id(db_session, model, server_id, seen_ids: set[int]) -> int:
    """Delete local rows for a server when their Jamf IDs are no longer present upstream."""
    query = delete(model).where(model.server_id == server_id)
    if seen_ids:
        query = query.where(model.jamf_id.not_in(seen_ids))
    result = await db_session.execute(query)
    return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Strategy 1: /api/v2/computers  (Jamf Pro 10.49+)
# Response has nested dicts: general{}, hardware{}, location{}
# ---------------------------------------------------------------------------


async def _sync_computers_v2(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int] | None:
    """Try the v2 computers endpoint. Returns upsert count or None if not available."""
    base_url = server.url
    headers = {"Authorization": f"Bearer {token}"}
    page, total_upserted = 0, 0
    created_count = 0
    updated_count = 0
    seen_ids: set[int] = set()

    while True:
        resp = await client.get(
            f"{base_url}/api/v2/computers",
            headers=headers,
            params={"page": page, "page-size": _PAGE_SIZE},
        )
        if resp.status_code in (404, 405):
            return None  # endpoint not available — try next strategy
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET /api/v2/computers page {page} returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for comp in results:
            # id may be int or string depending on Jamf version
            jamf_id = int(comp.get("id", 0))
            if not jamf_id:
                continue
            seen_ids.add(jamf_id)

            general = comp.get("general") or {}
            hardware = comp.get("hardware") or {}
            location = comp.get("location") or {}
            mdm = general.get("mdmCapable") or {}

            action = await _upsert_device(
                db_session,
                server.id,
                jamf_id,
                {
                    "name": general.get("name") or comp.get("name") or f"Computer {jamf_id}",
                    "udid": comp.get("udid"),
                    "management_id": general.get("managementId"),
                    "serial_number": comp.get("serialNumber"),
                    "model": hardware.get("model"),
                    "os_version": hardware.get("osVersion"),
                    "os_build": hardware.get("osBuild"),
                    "processor": hardware.get("processorType"),
                    "ram_mb": hardware.get("totalRamMegabytes"),
                    "is_managed": bool(mdm.get("capable", False)),
                    "is_supervised": bool(general.get("supervised", False)),
                    "last_contact": _parse_dt(general.get("lastContactTime")),
                    "username": location.get("username"),
                    "full_name": location.get("realname"),
                    "email": location.get("emailAddress"),
                    "department": location.get("department"),
                    "building": location.get("building"),
                },
            )
            if action == "created":
                created_count += 1
            else:
                updated_count += 1
            total_upserted += 1

        await db_session.flush()

        total_count = data.get("totalCount", 0)
        if (page + 1) * _PAGE_SIZE >= total_count:
            break
        page += 1

    deleted = await _purge_missing_by_jamf_id(db_session, Device, server.id, seen_ids)

    logger.info(
        "v2 sync: %d computers from %s (deleted stale: %d)", total_upserted, base_url, deleted
    )
    return created_count, updated_count, deleted


# ---------------------------------------------------------------------------
# Strategy 2: /api/v1/computers-preview  (Jamf Pro 10.32–10.48)
# Flat JSON response
# ---------------------------------------------------------------------------


async def _sync_computers_v1(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int] | None:
    """Try the v1 computers-preview endpoint. Returns count or None."""
    base_url = server.url
    headers = {"Authorization": f"Bearer {token}"}
    page, total_upserted = 0, 0
    created_count = 0
    updated_count = 0
    seen_ids: set[int] = set()

    while True:
        resp = await client.get(
            f"{base_url}/api/v1/computers-preview",
            headers=headers,
            params={"page": page, "page-size": _PAGE_SIZE},
        )
        if resp.status_code in (404, 405):
            return None
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET /api/v1/computers-preview page {page} returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        for comp in results:
            jamf_id = int(comp.get("id", 0))
            if not jamf_id:
                continue
            seen_ids.add(jamf_id)

            action = await _upsert_device(
                db_session,
                server.id,
                jamf_id,
                {
                    "name": comp.get("name") or f"Computer {jamf_id}",
                    "udid": comp.get("udid"),
                    "management_id": comp.get("managementId"),
                    "serial_number": comp.get("serialNumber"),
                    "model": comp.get("model"),
                    "os_version": comp.get("osVersion"),
                    "os_build": comp.get("osBuild"),
                    "is_managed": bool(comp.get("managed", False)),
                    "is_supervised": bool(comp.get("supervised", False)),
                    "last_contact": _parse_dt(comp.get("lastContactTime")),
                    "username": comp.get("username"),
                    "full_name": comp.get("realName"),
                    "email": comp.get("email"),
                    "department": comp.get("departmentName"),
                    "building": comp.get("buildingName"),
                    "site": (comp.get("site") or {}).get("name"),
                },
            )
            if action == "created":
                created_count += 1
            else:
                updated_count += 1
            total_upserted += 1

        await db_session.flush()

        total_count = data.get("totalCount", 0)
        if (page + 1) * _PAGE_SIZE >= total_count:
            break
        page += 1

    deleted = await _purge_missing_by_jamf_id(db_session, Device, server.id, seen_ids)

    logger.info(
        "v1 sync: %d computers from %s (deleted stale: %d)", total_upserted, base_url, deleted
    )
    return created_count, updated_count, deleted


# ---------------------------------------------------------------------------
# Strategy 3: /JSSResource/computers  (Classic API — all versions)
# Fetches list for IDs, then per-device detail for hardware/OS fields
# ---------------------------------------------------------------------------


async def _fetch_computer_detail_classic(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    jamf_id: int,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    async with semaphore:
        try:
            resp = await client.get(
                f"{base_url}/JSSResource/computers/id/{jamf_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.warning("Skipping computer %d detail: HTTP %d", jamf_id, resp.status_code)
                return None
            return resp.json().get("computer", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error fetching computer %d detail: %s", jamf_id, exc)
            return None


async def _sync_computers_classic(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int]:
    """Fall back to classic Jamf API. Fetches per-device detail for full hardware info."""
    base_url = server.url
    resp = await client.get(
        f"{base_url}/JSSResource/computers",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"GET /JSSResource/computers returned {resp.status_code}: {resp.text[:200]}"
        )

    stubs = resp.json().get("computers", [])
    valid_ids = [int(c["id"]) for c in stubs if c.get("id")]
    seen_ids = set(valid_ids)

    # Fetch full detail concurrently (max 10 in-flight)
    semaphore = asyncio.Semaphore(10)
    details = await asyncio.gather(
        *[
            _fetch_computer_detail_classic(client, base_url, token, jid, semaphore)
            for jid in valid_ids
        ]
    )

    total_upserted = 0
    created_count = 0
    updated_count = 0
    for jamf_id, detail in zip(valid_ids, details, strict=False):
        if detail is None:
            continue

        general = detail.get("general") or {}
        hardware = detail.get("hardware") or {}
        location = detail.get("location") or {}
        remote_mgmt = general.get("remote_management") or {}

        action = await _upsert_device(
            db_session,
            server.id,
            jamf_id,
            {
                "name": general.get("name") or f"Computer {jamf_id}",
                "udid": general.get("udid"),
                "serial_number": general.get("serial_number"),
                "asset_tag": general.get("asset_tag") or None,
                "model": hardware.get("model"),
                "model_identifier": hardware.get("model_identifier"),
                "os_version": hardware.get("os_version"),
                "os_build": hardware.get("os_build"),
                "processor": hardware.get("processor_type"),
                "ram_mb": hardware.get("total_ram") or None,
                "is_managed": bool(remote_mgmt.get("managed", general.get("managed", False))),
                "is_supervised": bool(general.get("supervised", False)),
                "last_contact": _parse_dt(general.get("last_contact_time_utc")),
                "last_enrollment": _parse_dt(general.get("last_enrolled_date_utc")),
                "username": location.get("username"),
                "full_name": location.get("realname") or location.get("real_name"),
                "email": location.get("email_address"),
                "department": location.get("department"),
                "building": location.get("building"),
            },
        )
        if action == "created":
            created_count += 1
        else:
            updated_count += 1
        total_upserted += 1

    await db_session.flush()
    deleted = await _purge_missing_by_jamf_id(db_session, Device, server.id, seen_ids)
    logger.info(
        "classic sync: %d computers from %s (deleted stale: %d)", total_upserted, base_url, deleted
    )
    return created_count, updated_count, deleted


# ---------------------------------------------------------------------------
# Dispatcher — tries strategies in order
# ---------------------------------------------------------------------------


async def _sync_computers(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int]:
    for strategy in (_sync_computers_v2, _sync_computers_v1):
        result = await strategy(db_session, server, client, token)
        if result is not None:
            return result
    # All modern endpoints unavailable — fall back to classic
    logger.warning("Modern computer endpoints unavailable on %s, using classic API", server.url)
    return await _sync_computers_classic(db_session, server, client, token)


# ---------------------------------------------------------------------------
# Policy sync — Jamf Pro REST API (/api/v1/policies), Classic fallback
# ---------------------------------------------------------------------------


async def _upsert_policy(db_session, server_id, jamf_id: int, fields: dict) -> str:
    existing = await db_session.execute(
        select(Policy).where(Policy.jamf_id == jamf_id, Policy.server_id == server_id)
    )
    policies = existing.scalars().all()
    action = "updated"
    if not policies:
        policy = Policy(jamf_id=jamf_id, server_id=server_id)
        db_session.add(policy)
        action = "created"
    else:
        policy = policies[0]
        for dup in policies[1:]:
            await db_session.delete(dup)

    for attr, value in fields.items():
        setattr(policy, attr, value)
    policy.synced_at = datetime.now(UTC)
    return action


def _scope_description_from_modern(scope: dict) -> str | None:
    """Build a human-readable scope string from the Jamf Pro REST API scope object."""
    parts: list[str] = []
    if scope.get("allComputers") or scope.get("all_computers"):
        parts.append("All Computers")
    computers = scope.get("computers") or []
    if computers:
        parts.append(f"{len(computers)} computer(s)")
    groups = scope.get("computerGroups") or scope.get("computer_groups") or []
    if groups:
        names = [g.get("name", "") for g in groups if g.get("name")]
        if names:
            parts.append("Groups: " + ", ".join(names))
    return "; ".join(parts) if parts else None


async def _fetch_policy_detail_v1(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    policy_id: str,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """Fetch a single policy's full detail from the Jamf Pro REST API."""
    async with semaphore:
        try:
            resp = await client.get(
                f"{base_url}/api/v1/policies/{policy_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.warning(
                    "Skipping policy %s (v1 detail): HTTP %d", policy_id, resp.status_code
                )
                return None
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error fetching policy detail %s (v1): %s", policy_id, exc)
            return None


async def _sync_policies_v1(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int] | None:
    """Sync policies via the Jamf Pro REST API (/api/v1/policies).

    Returns the upsert count, or None if the endpoint is not available.
    """
    base_url = server.url
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    page, total_upserted = 0, 0

    # Collect all policy stubs via pagination
    all_stubs: list[dict] = []
    while True:
        resp = await client.get(
            f"{base_url}/api/v1/policies",
            headers=headers,
            params={"page": page, "page-size": _PAGE_SIZE},
        )
        if resp.status_code in (404, 405):
            return None  # endpoint not available — fall back to Classic API
        if resp.status_code != 200:
            raise RuntimeError(
                f"GET /api/v1/policies page {page} returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        all_stubs.extend(results)

        total_count = data.get("totalCount", 0)
        if (page + 1) * _PAGE_SIZE >= total_count:
            break
        page += 1

    if not all_stubs:
        logger.info("No policies found via /api/v1/policies on %s", base_url)
        deleted = await _purge_missing_by_jamf_id(db_session, Policy, server.id, set())
        logger.info("v1 policy sync: 0 policies from %s (deleted stale: %d)", base_url, deleted)
        return 0, 0, deleted

    seen_ids = {int(s["id"]) for s in all_stubs if s.get("id")}
    created_count = 0
    updated_count = 0

    # Fetch full detail for each policy concurrently (max 10 in-flight)
    semaphore = asyncio.Semaphore(10)
    stub_ids = [str(s.get("id", "")) for s in all_stubs if s.get("id")]
    details = await asyncio.gather(
        *[_fetch_policy_detail_v1(client, base_url, token, pid, semaphore) for pid in stub_ids]
    )

    for stub_id, detail in zip(stub_ids, details, strict=False):
        jamf_id = int(stub_id)
        if not jamf_id:
            continue

        # Use detail fields if available, else fall back to stub
        stub = next((s for s in all_stubs if str(s.get("id")) == stub_id), {})
        src = detail or stub

        general = src.get("general") or src  # v1 may be flat or nested
        scope = src.get("scope") or {}

        action = await _upsert_policy(
            db_session,
            server.id,
            jamf_id,
            {
                "name": general.get("name") or src.get("name") or f"Policy {jamf_id}",
                "enabled": bool(general.get("enabled", src.get("enabled", True))),
                "category": (general.get("category") or {}).get("name")
                or src.get("categoryName")
                or None,
                "trigger": general.get("trigger") or src.get("trigger") or None,
                "scope_description": _scope_description_from_modern(scope),
                "payload_description": None,
            },
        )
        if action == "created":
            created_count += 1
        else:
            updated_count += 1
        total_upserted += 1

    await db_session.flush()
    deleted = await _purge_missing_by_jamf_id(db_session, Policy, server.id, seen_ids)
    logger.info(
        "v1 policy sync: %d policies from %s (deleted stale: %d)", total_upserted, base_url, deleted
    )
    return created_count, updated_count, deleted


async def _fetch_policy_detail_classic(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    policy_id: int,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """Fetch a single policy's full detail from the Classic API."""
    async with semaphore:
        try:
            resp = await client.get(
                f"{base_url}/JSSResource/policies/id/{policy_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.warning(
                    "Skipping policy %d (classic detail): HTTP %d", policy_id, resp.status_code
                )
                return None
            return resp.json().get("policy", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error fetching policy detail %d (classic): %s", policy_id, exc)
            return None


async def _sync_policies_classic(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int]:
    """Sync policies via the Classic API (/JSSResource/policies). Always available."""
    base_url = server.url
    resp = await client.get(
        f"{base_url}/JSSResource/policies",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"GET /JSSResource/policies returned {resp.status_code}: {resp.text[:200]}"
        )

    raw = resp.json()
    # Classic API returns either {"policies": [...]} or {"policies": {"policy": [...]}}
    policies_val = raw.get("policies") or []
    if isinstance(policies_val, dict):
        policy_stubs = policies_val.get("policy") or []
    else:
        policy_stubs = policies_val

    if not policy_stubs:
        logger.info("No policies found via Classic API on %s", base_url)
        deleted = await _purge_missing_by_jamf_id(db_session, Policy, server.id, set())
        logger.info(
            "classic policy sync: 0 policies from %s (deleted stale: %d)", base_url, deleted
        )
        return 0, 0, deleted

    valid_stubs = [s for s in policy_stubs if s.get("id")]
    seen_ids = {int(s["id"]) for s in valid_stubs}
    created_count = 0
    updated_count = 0
    semaphore = asyncio.Semaphore(10)
    details = await asyncio.gather(
        *[
            _fetch_policy_detail_classic(client, base_url, token, int(s["id"]), semaphore)
            for s in valid_stubs
        ]
    )

    total_upserted = 0
    for stub, detail in zip(valid_stubs, details, strict=False):
        jamf_id = int(stub.get("id", 0))
        if not jamf_id or detail is None:
            continue

        general = detail.get("general") or {}
        scope = detail.get("scope") or {}

        scope_parts: list[str] = []
        if scope.get("all_computers"):
            scope_parts.append("All Computers")
        computers = scope.get("computers") or []
        if computers:
            scope_parts.append(f"{len(computers)} computer(s)")
        groups = scope.get("computer_groups") or []
        if groups:
            names = [g.get("name", "") for g in groups if g.get("name")]
            if names:
                scope_parts.append("Groups: " + ", ".join(names))

        action = await _upsert_policy(
            db_session,
            server.id,
            jamf_id,
            {
                "name": general.get("name") or stub.get("name") or f"Policy {jamf_id}",
                "enabled": bool(general.get("enabled", True)),
                "category": (general.get("category") or {}).get("name") or None,
                "trigger": general.get("trigger") or None,
                "scope_description": "; ".join(scope_parts) if scope_parts else None,
                "payload_description": None,
            },
        )
        if action == "created":
            created_count += 1
        else:
            updated_count += 1
        total_upserted += 1

    await db_session.flush()
    deleted = await _purge_missing_by_jamf_id(db_session, Policy, server.id, seen_ids)
    logger.info(
        "classic policy sync: %d policies from %s (deleted stale: %d)",
        total_upserted,
        base_url,
        deleted,
    )
    return created_count, updated_count, deleted


async def _sync_policies(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int]:
    """Sync policies: try Jamf Pro REST API first, fall back to Classic API."""
    result = await _sync_policies_v1(db_session, server, client, token)
    if result is not None:
        return result
    logger.warning(
        "Jamf Pro REST API policy endpoint unavailable on %s, using Classic API", server.url
    )
    return await _sync_policies_classic(db_session, server, client, token)


# ---------------------------------------------------------------------------
# Smart group sync — Classic API (/JSSResource/computergroups)
# ---------------------------------------------------------------------------


async def _upsert_smart_group(db_session, server_id, jamf_id: int, fields: dict) -> str:
    existing = await db_session.execute(
        select(SmartGroup).where(SmartGroup.jamf_id == jamf_id, SmartGroup.server_id == server_id)
    )
    groups = existing.scalars().all()
    action = "updated"
    if not groups:
        sg = SmartGroup(jamf_id=jamf_id, server_id=server_id)
        db_session.add(sg)
        action = "created"
    else:
        sg = groups[0]
        for dup in groups[1:]:
            await db_session.delete(dup)
    for attr, value in fields.items():
        setattr(sg, attr, value)
    sg.synced_at = datetime.now(UTC)
    return action


async def _fetch_smart_group_detail(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    group_id: int,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    async with semaphore:
        try:
            resp = await client.get(
                f"{base_url}/JSSResource/computergroups/id/{group_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.warning("Skipping group %d: HTTP %d", group_id, resp.status_code)
                return None
            return resp.json().get("computer_group", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error fetching group detail %d: %s", group_id, exc)
            return None


async def _sync_smart_groups(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int]:
    """Sync computer smart groups via the Classic API."""
    base_url = server.url
    resp = await client.get(
        f"{base_url}/JSSResource/computergroups",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        logger.warning("GET /JSSResource/computergroups returned %d — skipping", resp.status_code)
        return 0, 0, 0

    raw = resp.json()
    # Response is either {"computer_groups": [...]} or {"computer_groups": {"computer_group": [...]}}
    groups_val = raw.get("computer_groups") or []
    if isinstance(groups_val, dict):
        all_groups = groups_val.get("computer_group") or []
    else:
        all_groups = groups_val

    # Only smart groups
    smart_stubs = [g for g in all_groups if g.get("is_smart") or g.get("is_smart_group")]
    if not smart_stubs:
        logger.info("No smart groups found on %s", base_url)
        deleted = await _purge_missing_by_jamf_id(db_session, SmartGroup, server.id, set())
        logger.info("smart group sync: 0 groups from %s (deleted stale: %d)", base_url, deleted)
        return 0, 0, deleted

    seen_ids = {int(g["id"]) for g in smart_stubs if g.get("id")}
    created_count = 0
    updated_count = 0

    semaphore = asyncio.Semaphore(10)
    details = await asyncio.gather(
        *[
            _fetch_smart_group_detail(client, base_url, token, int(g["id"]), semaphore)
            for g in smart_stubs
            if g.get("id")
        ]
    )

    total_upserted = 0
    for stub, detail in zip(smart_stubs, details, strict=False):
        jamf_id = int(stub.get("id", 0))
        if not jamf_id or detail is None:
            continue

        criteria_raw = detail.get("criteria") or {}
        if isinstance(criteria_raw, dict):
            # Classic API wraps criteria in {"criterion": [...]}
            crit_list = criteria_raw.get("criterion") or []
            if isinstance(crit_list, dict):  # single criterion comes as dict, not list
                crit_list = [crit_list]
            criteria = crit_list
        elif isinstance(criteria_raw, list):
            criteria = criteria_raw
        else:
            criteria = []

        computers_raw = detail.get("computers") or {}
        if isinstance(computers_raw, dict):
            comp_list = computers_raw.get("computer") or []
            if isinstance(comp_list, dict):
                comp_list = [comp_list]
            member_count = detail.get("size") or len(comp_list)
        else:
            member_count = detail.get("size") or len(computers_raw)

        action = await _upsert_smart_group(
            db_session,
            server.id,
            jamf_id,
            {
                "name": detail.get("name") or stub.get("name") or f"Group {jamf_id}",
                "criteria": criteria if criteria else None,
                "member_count": member_count,
            },
        )
        if action == "created":
            created_count += 1
        else:
            updated_count += 1
        total_upserted += 1

    await db_session.flush()
    deleted = await _purge_missing_by_jamf_id(db_session, SmartGroup, server.id, seen_ids)
    logger.info(
        "smart group sync: %d groups from %s (deleted stale: %d)", total_upserted, base_url, deleted
    )
    return created_count, updated_count, deleted


# ---------------------------------------------------------------------------
# Patch title sync — modern API first, Classic fallback
# ---------------------------------------------------------------------------


async def _upsert_patch_title(db_session, server_id, jamf_id: int, fields: dict) -> str:
    existing = await db_session.execute(
        select(PatchTitle).where(PatchTitle.jamf_id == jamf_id, PatchTitle.server_id == server_id)
    )
    patch_titles = existing.scalars().all()
    action = "updated"
    if not patch_titles:
        pt = PatchTitle(jamf_id=jamf_id, server_id=server_id)
        db_session.add(pt)
        action = "created"
    else:
        pt = patch_titles[0]
        for dup in patch_titles[1:]:
            await db_session.delete(dup)
    for attr, value in fields.items():
        setattr(pt, attr, value)
    pt.synced_at = datetime.now(UTC)
    return action


async def _sync_patches_modern(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int] | None:
    """Sync patch titles via /api/v2/patch-software-title-configurations.

    Returns upsert count, or None if endpoint is unavailable.
    """
    base_url = server.url
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    total_upserted = 0

    # First request — determine if the response is a paginated wrapper or a bare array
    resp = await client.get(
        f"{base_url}/api/v2/patch-software-title-configurations",
        headers=headers,
        params={"page": 0, "page-size": _PAGE_SIZE},
    )
    if resp.status_code in (404, 405):
        return None
    if resp.status_code != 200:
        raise RuntimeError(
            f"GET /api/v2/patch-software-title-configurations returned "
            f"{resp.status_code}: {resp.text[:200]}"
        )

    raw = resp.json()

    # Jamf Cloud returns a bare array; Jamf Pro 11+/paginated returns {results, totalCount}
    if isinstance(raw, list):
        all_items = raw
    else:
        all_items = raw.get("results") or []
        total_count = raw.get("totalCount", 0)
        page = 1
        while (page * _PAGE_SIZE) < total_count:
            r = await client.get(
                f"{base_url}/api/v2/patch-software-title-configurations",
                headers=headers,
                params={"page": page, "page-size": _PAGE_SIZE},
            )
            if r.status_code != 200:
                break
            all_items.extend(r.json().get("results") or [])
            page += 1

    seen_ids = {
        int(item.get("id", 0) or 0)
        for item in all_items
        if isinstance(item, dict) and item.get("id")
    }
    created_count = 0
    updated_count = 0

    for item in all_items:
        if not isinstance(item, dict):
            continue
        jamf_id = int(item.get("id", 0) or 0)
        if not jamf_id:
            continue
        enrolled = int(item.get("enrolledDeviceCount") or 0)
        installed = int(item.get("installedDeviceCount") or 0)
        action = await _upsert_patch_title(
            db_session,
            server.id,
            jamf_id,
            {
                "software_title": item.get("softwareTitleName") or f"Title {jamf_id}",
                "latest_version": item.get("targetPatchVersion") or None,
                "current_version": item.get("targetPatchVersion") or None,
                "patched_count": installed,
                "unpatched_count": max(enrolled - installed, 0),
            },
        )
        if action == "created":
            created_count += 1
        else:
            updated_count += 1
        total_upserted += 1

    await db_session.flush()
    deleted = await _purge_missing_by_jamf_id(db_session, PatchTitle, server.id, seen_ids)
    logger.info(
        "modern patch sync: %d titles from %s (deleted stale: %d)",
        total_upserted,
        base_url,
        deleted,
    )
    return created_count, updated_count, deleted


async def _sync_patches_classic(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int]:
    """Sync patch titles via the Classic API (/JSSResource/patchsoftwaretitles)."""
    base_url = server.url
    resp = await client.get(
        f"{base_url}/JSSResource/patchsoftwaretitles",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        logger.warning(
            "GET /JSSResource/patchsoftwaretitles returned %d — skipping", resp.status_code
        )
        return 0, 0, 0

    raw = resp.json()
    titles_val = raw.get("patch_software_titles") or raw.get("patchSoftwareTitles") or []
    if isinstance(titles_val, dict):
        stubs = titles_val.get("patch_software_title") or []
    else:
        stubs = titles_val

    seen_ids = {int(stub.get("id", 0)) for stub in stubs if stub.get("id")}
    created_count = 0
    updated_count = 0

    total_upserted = 0
    for stub in stubs:
        jamf_id = int(stub.get("id", 0))
        if not jamf_id:
            continue
        action = await _upsert_patch_title(
            db_session,
            server.id,
            jamf_id,
            {
                "software_title": stub.get("name") or f"Title {jamf_id}",
                "latest_version": stub.get("current_version") or None,
                "current_version": stub.get("current_version") or None,
                "patched_count": 0,
                "unpatched_count": 0,
            },
        )
        if action == "created":
            created_count += 1
        else:
            updated_count += 1
        total_upserted += 1

    await db_session.flush()
    deleted = await _purge_missing_by_jamf_id(db_session, PatchTitle, server.id, seen_ids)
    logger.info(
        "classic patch sync: %d titles from %s (deleted stale: %d)",
        total_upserted,
        base_url,
        deleted,
    )
    return created_count, updated_count, deleted


async def _sync_patches(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> tuple[int, int, int]:
    """Sync patch titles: modern API first, Classic fallback."""
    result = await _sync_patches_modern(db_session, server, client, token)
    if result is not None:
        return result
    logger.warning("Modern patch endpoint unavailable on %s, using Classic API", server.url)
    return await _sync_patches_classic(db_session, server, client, token)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def sync_server(server_id: str) -> None:
    """Full sync for one Jamf Pro server. Runs as a fire-and-forget task."""
    await _set_status(server_id, "running")

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(JamfServer).where(JamfServer.id == server_id)  # type: ignore[arg-type]
            )
            server = result.scalar_one_or_none()
            if server is None:
                logger.error("sync_server: server %s not found", server_id)
                await _set_status(server_id, "error")
                return

            client_id = decrypt(server.client_id)
            client_secret = decrypt(server.client_secret)

            async with httpx.AsyncClient(timeout=120) as http:
                token = await _get_oauth_token(http, server.url, client_id, client_secret)
                device_created, device_updated, device_deleted = await _sync_computers(
                    db, server, http, token
                )
                policy_created, policy_updated, policy_deleted = await _sync_policies(
                    db, server, http, token
                )
                sg_created, sg_updated, sg_deleted = await _sync_smart_groups(
                    db, server, http, token
                )
                patch_created, patch_updated, patch_deleted = await _sync_patches(
                    db, server, http, token
                )

            server.last_sync = datetime.now(UTC)
            server.last_sync_error = None
            await db.commit()

            await _set_sync_result(
                server_id,
                {
                    "finished_at": datetime.now(UTC).isoformat(),
                    "status": "success",
                    "devices": {
                        "created": device_created,
                        "updated": device_updated,
                        "deleted": device_deleted,
                    },
                    "policies": {
                        "created": policy_created,
                        "updated": policy_updated,
                        "deleted": policy_deleted,
                    },
                    "smart_groups": {
                        "created": sg_created,
                        "updated": sg_updated,
                        "deleted": sg_deleted,
                    },
                    "patch_titles": {
                        "created": patch_created,
                        "updated": patch_updated,
                        "deleted": patch_deleted,
                    },
                },
            )

            device_total = device_created + device_updated
            policy_total = policy_created + policy_updated
            sg_total = sg_created + sg_updated
            patch_total = patch_created + patch_updated

            logger.info(
                "Sync complete: server=%s "
                "devices(c=%d,u=%d,d=%d,total=%d) "
                "policies(c=%d,u=%d,d=%d,total=%d) "
                "smart_groups(c=%d,u=%d,d=%d,total=%d) "
                "patches(c=%d,u=%d,d=%d,total=%d)",
                server_id,
                device_created,
                device_updated,
                device_deleted,
                device_total,
                policy_created,
                policy_updated,
                policy_deleted,
                policy_total,
                sg_created,
                sg_updated,
                sg_deleted,
                sg_total,
                patch_created,
                patch_updated,
                patch_deleted,
                patch_total,
            )
            await _set_status(server_id, "idle")

        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            error_msg = str(exc)
            logger.error("Sync failed: server=%s error=%s", server_id, error_msg)

            await _set_sync_result(
                server_id,
                {
                    "finished_at": datetime.now(UTC).isoformat(),
                    "status": "error",
                    "error": error_msg[:500],
                },
            )

            # Persist error to the server row
            try:
                async with AsyncSessionLocal() as db2:
                    result2 = await db2.execute(
                        select(JamfServer).where(JamfServer.id == server_id)  # type: ignore[arg-type]
                    )
                    srv2 = result2.scalar_one_or_none()
                    if srv2:
                        srv2.last_sync_error = error_msg[:500]
                        await db2.commit()
            except Exception:  # noqa: BLE001
                pass

            await _set_status(server_id, "error")


async def sync_all_servers() -> None:
    """Kick off sync for every active server concurrently."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(JamfServer).where(JamfServer.is_active.is_(True)))
        servers = result.scalars().all()

    await asyncio.gather(*(sync_server(str(s.id)) for s in servers), return_exceptions=True)
