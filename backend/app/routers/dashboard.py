"""Dashboard statistics router."""

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession
from app.models.device import Device
from app.models.patch import PatchTitle
from app.models.policy import Policy
from app.models.server import JamfServer
from app.models.smart_group import SmartGroup
from app.schemas.dashboard import DashboardStats, OsVersionCount, PatchSummary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    db: DBSession,
    _: CurrentUser,
    server_id: uuid.UUID | None = Query(None),
) -> DashboardStats:
    # ── Combined device counts (one query) ─────────────────────────────────
    device_q = select(
        func.count().label("total"),
        func.count().filter(Device.is_managed.is_(True)).label("managed"),
    )
    if server_id:
        device_q = device_q.where(Device.server_id == server_id)
    device_row = (await db.execute(device_q)).one()
    total_devices: int = device_row.total
    managed_devices: int = device_row.managed

    # ── Combined policy counts (one query) ─────────────────────────────────
    policy_q = select(
        func.count().label("total"),
        func.count().filter(Policy.enabled.is_(True)).label("enabled"),
    )
    if server_id:
        policy_q = policy_q.where(Policy.server_id == server_id)
    policy_row = (await db.execute(policy_q)).one()
    total_policies: int = policy_row.total
    enabled_policies: int = policy_row.enabled

    # ── Combined patch counts (one query) ──────────────────────────────────
    patch_q = select(
        func.count().label("total"),
        func.coalesce(func.sum(PatchTitle.unpatched_count), 0).label("unpatched"),
    )
    if server_id:
        patch_q = patch_q.where(PatchTitle.server_id == server_id)
    patch_row = (await db.execute(patch_q)).one()
    total_patches: int = patch_row.total
    unpatched_count: int = patch_row.unpatched

    # ── Smart group count ──────────────────────────────────────────────────
    sg_q = select(func.count())
    if server_id:
        sg_q = sg_q.where(SmartGroup.server_id == server_id)
    else:
        sg_q = sg_q.select_from(SmartGroup)
    total_smart_groups: int = (await db.execute(sg_q)).scalar_one()

    # ── Combined server counts (one query) ─────────────────────────────────
    server_q = select(
        func.count().label("total"),
        func.count().filter(JamfServer.is_active.is_(True)).label("active"),
    )
    server_row = (await db.execute(server_q)).one()
    total_servers: int = server_row.total
    active_servers: int = server_row.active

    # ── OS distribution ────────────────────────────────────────────────────
    os_dist_q = (
        select(Device.os_version, func.count().label("cnt"))
        .where(Device.os_version.isnot(None))
        .group_by(Device.os_version)
        .order_by(func.count().desc())
        .limit(10)
    )
    if server_id:
        os_dist_q = os_dist_q.where(Device.server_id == server_id)
    os_distribution = [
        OsVersionCount(os_version=row[0], count=row[1]) for row in await db.execute(os_dist_q)
    ]

    # ── Top patch titles ───────────────────────────────────────────────────
    patch_sum_q = (
        select(PatchTitle.software_title, PatchTitle.patched_count, PatchTitle.unpatched_count)
        .order_by((PatchTitle.patched_count + PatchTitle.unpatched_count).desc())
        .limit(10)
    )
    if server_id:
        patch_sum_q = patch_sum_q.where(PatchTitle.server_id == server_id)
    top_patches = [
        PatchSummary(software_title=row[0], patched=row[1], unpatched=row[2])
        for row in await db.execute(patch_sum_q)
    ]

    return DashboardStats(
        total_devices=total_devices,
        managed_devices=managed_devices,
        total_policies=total_policies,
        enabled_policies=enabled_policies,
        total_patches=total_patches,
        unpatched_count=unpatched_count,
        total_smart_groups=total_smart_groups,
        total_servers=total_servers,
        active_servers=active_servers,
        os_distribution=os_distribution,
        top_patches=top_patches,
    )
