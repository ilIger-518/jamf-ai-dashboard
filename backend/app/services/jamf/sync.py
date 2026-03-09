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
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from app.cache import get_redis
from app.database import AsyncSessionLocal
from app.models.device import Device
from app.models.policy import Policy
from app.models.server import JamfServer
from app.services.encryption import decrypt

logger = logging.getLogger(__name__)

_PAGE_SIZE = 200
_SYNC_STATUS_TTL = 3600  # Redis key TTL in seconds


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def _redis_key(server_id: str) -> str:
    return f"sync:status:{server_id}"


async def get_sync_status(server_id: str) -> str:
    """Return 'running', 'idle', or 'error' from Redis (default: 'idle')."""
    redis = await get_redis()
    val = await redis.get(_redis_key(server_id))
    return val.decode() if val else "idle"


async def _set_status(server_id: str, status: str) -> None:
    redis = await get_redis()
    await redis.set(_redis_key(server_id), status, ex=_SYNC_STATUS_TTL)


# ---------------------------------------------------------------------------
# OAuth token
# ---------------------------------------------------------------------------

async def _get_oauth_token(client: httpx.AsyncClient, base_url: str, client_id: str, client_secret: str) -> str:
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
        raise RuntimeError(
            f"Jamf Pro OAuth failed ({resp.status_code}): {resp.text[:200]}"
        )
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


async def _upsert_device(db_session, server_id, jamf_id: int, fields: dict) -> None:
    existing = await db_session.execute(
        select(Device).where(Device.jamf_id == jamf_id, Device.server_id == server_id)
    )
    device = existing.scalar_one_or_none()
    if device is None:
        device = Device(jamf_id=jamf_id, server_id=server_id)
        db_session.add(device)

    for attr, value in fields.items():
        setattr(device, attr, value)
    device.synced_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Strategy 1: /api/v2/computers  (Jamf Pro 10.49+)
# Response has nested dicts: general{}, hardware{}, location{}
# ---------------------------------------------------------------------------

async def _sync_computers_v2(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> int | None:
    """Try the v2 computers endpoint. Returns upsert count or None if not available."""
    base_url = server.url
    headers = {"Authorization": f"Bearer {token}"}
    page, total_upserted = 0, 0

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

            general = comp.get("general") or {}
            hardware = comp.get("hardware") or {}
            location = comp.get("location") or {}
            mdm = general.get("mdmCapable") or {}

            await _upsert_device(db_session, server.id, jamf_id, {
                "name": general.get("name") or comp.get("name") or f"Computer {jamf_id}",
                "udid": comp.get("udid"),
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
            })
            total_upserted += 1

        await db_session.flush()

        total_count = data.get("totalCount", 0)
        if (page + 1) * _PAGE_SIZE >= total_count:
            break
        page += 1

    logger.info("v2 sync: %d computers from %s", total_upserted, base_url)
    return total_upserted


# ---------------------------------------------------------------------------
# Strategy 2: /api/v1/computers-preview  (Jamf Pro 10.32–10.48)
# Flat JSON response
# ---------------------------------------------------------------------------

async def _sync_computers_v1(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> int | None:
    """Try the v1 computers-preview endpoint. Returns count or None."""
    base_url = server.url
    headers = {"Authorization": f"Bearer {token}"}
    page, total_upserted = 0, 0

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

            await _upsert_device(db_session, server.id, jamf_id, {
                "name": comp.get("name") or f"Computer {jamf_id}",
                "udid": comp.get("udid"),
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
            })
            total_upserted += 1

        await db_session.flush()

        total_count = data.get("totalCount", 0)
        if (page + 1) * _PAGE_SIZE >= total_count:
            break
        page += 1

    logger.info("v1 sync: %d computers from %s", total_upserted, base_url)
    return total_upserted


# ---------------------------------------------------------------------------
# Strategy 3: /JSSResource/computers  (Classic API — all versions)
# Returns all computers in one call, basic fields only
# ---------------------------------------------------------------------------

async def _sync_computers_classic(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> int:
    """Fall back to classic Jamf API. Returns upsert count."""
    base_url = server.url
    resp = await client.get(
        f"{base_url}/JSSResource/computers",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"GET /JSSResource/computers returned {resp.status_code}: {resp.text[:200]}"
        )

    computers = resp.json().get("computers", [])
    total_upserted = 0

    for comp in computers:
        jamf_id = int(comp.get("id", 0))
        if not jamf_id:
            continue

        await _upsert_device(db_session, server.id, jamf_id, {
            "name": comp.get("name") or f"Computer {jamf_id}",
            "udid": comp.get("udid"),
            "serial_number": comp.get("serial_number"),
            "model": comp.get("model"),
            "os_version": comp.get("os_version"),
            "is_managed": bool(comp.get("managed", False)),
            "is_supervised": bool(comp.get("supervised", False)),
            "username": comp.get("username"),
            "full_name": comp.get("realname"),
            "email": comp.get("email_address"),
            "department": comp.get("department"),
            "building": comp.get("building"),
        })
        total_upserted += 1

    await db_session.flush()
    logger.info("classic sync: %d computers from %s", total_upserted, base_url)
    return total_upserted


# ---------------------------------------------------------------------------
# Dispatcher — tries strategies in order
# ---------------------------------------------------------------------------

async def _sync_computers(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> int:
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

async def _upsert_policy(db_session, server_id, jamf_id: int, fields: dict) -> None:
    existing = await db_session.execute(
        select(Policy).where(Policy.jamf_id == jamf_id, Policy.server_id == server_id)
    )
    policy = existing.scalar_one_or_none()
    if policy is None:
        policy = Policy(jamf_id=jamf_id, server_id=server_id)
        db_session.add(policy)

    for attr, value in fields.items():
        setattr(policy, attr, value)
    policy.synced_at = datetime.now(UTC)


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
                logger.warning("Skipping policy %s (v1 detail): HTTP %d", policy_id, resp.status_code)
                return None
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error fetching policy detail %s (v1): %s", policy_id, exc)
            return None


async def _sync_policies_v1(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> int | None:
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
        return 0

    # Fetch full detail for each policy concurrently (max 10 in-flight)
    semaphore = asyncio.Semaphore(10)
    stub_ids = [str(s.get("id", "")) for s in all_stubs if s.get("id")]
    details = await asyncio.gather(
        *[_fetch_policy_detail_v1(client, base_url, token, pid, semaphore) for pid in stub_ids]
    )

    for stub_id, detail in zip(stub_ids, details):
        jamf_id = int(stub_id)
        if not jamf_id:
            continue

        # Use detail fields if available, else fall back to stub
        stub = next((s for s in all_stubs if str(s.get("id")) == stub_id), {})
        src = detail or stub

        general = src.get("general") or src  # v1 may be flat or nested
        scope = src.get("scope") or {}

        await _upsert_policy(db_session, server.id, jamf_id, {
            "name": general.get("name") or src.get("name") or f"Policy {jamf_id}",
            "enabled": bool(general.get("enabled", src.get("enabled", True))),
            "category": (general.get("category") or {}).get("name")
                        or src.get("categoryName")
                        or None,
            "trigger": general.get("trigger") or src.get("trigger") or None,
            "scope_description": _scope_description_from_modern(scope),
            "payload_description": None,
        })
        total_upserted += 1

    await db_session.flush()
    logger.info("v1 policy sync: %d policies from %s", total_upserted, base_url)
    return total_upserted


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
                logger.warning("Skipping policy %d (classic detail): HTTP %d", policy_id, resp.status_code)
                return None
            return resp.json().get("policy", {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Error fetching policy detail %d (classic): %s", policy_id, exc)
            return None


async def _sync_policies_classic(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> int:
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
        return 0

    valid_stubs = [s for s in policy_stubs if s.get("id")]
    semaphore = asyncio.Semaphore(10)
    details = await asyncio.gather(
        *[
            _fetch_policy_detail_classic(client, base_url, token, int(s["id"]), semaphore)
            for s in valid_stubs
        ]
    )

    total_upserted = 0
    for stub, detail in zip(valid_stubs, details):
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

        await _upsert_policy(db_session, server.id, jamf_id, {
            "name": general.get("name") or stub.get("name") or f"Policy {jamf_id}",
            "enabled": bool(general.get("enabled", True)),
            "category": (general.get("category") or {}).get("name") or None,
            "trigger": general.get("trigger") or None,
            "scope_description": "; ".join(scope_parts) if scope_parts else None,
            "payload_description": None,
        })
        total_upserted += 1

    await db_session.flush()
    logger.info("classic policy sync: %d policies from %s", total_upserted, base_url)
    return total_upserted


async def _sync_policies(
    db_session, server: JamfServer, client: httpx.AsyncClient, token: str
) -> int:
    """Sync policies: try Jamf Pro REST API first, fall back to Classic API."""
    result = await _sync_policies_v1(db_session, server, client, token)
    if result is not None:
        return result
    logger.warning("Jamf Pro REST API policy endpoint unavailable on %s, using Classic API", server.url)
    return await _sync_policies_classic(db_session, server, client, token)


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

            async with httpx.AsyncClient(timeout=60) as http:
                token = await _get_oauth_token(http, server.url, client_id, client_secret)
                count = await _sync_computers(db, server, http, token)
                policy_count = await _sync_policies(db, server, http, token)

            server.last_sync = datetime.now(UTC)
            server.last_sync_error = None
            await db.commit()

            logger.info("Sync complete: server=%s devices=%d policies=%d", server_id, count, policy_count)
            await _set_status(server_id, "idle")

        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            error_msg = str(exc)
            logger.error("Sync failed: server=%s error=%s", server_id, error_msg)

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
        result = await db.execute(
            select(JamfServer).where(JamfServer.is_active.is_(True))
        )
        servers = result.scalars().all()

    await asyncio.gather(*(sync_server(str(s.id)) for s in servers), return_exceptions=True)
