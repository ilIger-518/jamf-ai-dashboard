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
    async def count(q) -> int:  # type: ignore[type-arg]
        r = await db.execute(select(func.count()).select_from(q.subquery()))
        return r.scalar_one()

    def dev_q():
        q = select(Device)
        if server_id:
            q = q.where(Device.server_id == server_id)
        return q

    def pol_q():
        q = select(Policy)
        if server_id:
            q = q.where(Policy.server_id == server_id)
        return q

    def patch_q():
        q = select(PatchTitle)
        if server_id:
            q = q.where(PatchTitle.server_id == server_id)
        return q

    def sg_q():
        q = select(SmartGroup)
        if server_id:
            q = q.where(SmartGroup.server_id == server_id)
        return q

    total_devices = await count(dev_q())
    managed_devices = await count(dev_q().where(Device.is_managed.is_(True)))
    total_policies = await count(pol_q())
    enabled_policies = await count(pol_q().where(Policy.enabled.is_(True)))
    total_patches = await count(patch_q())

    unpatched_q = select(func.sum(PatchTitle.unpatched_count))
    if server_id:
        unpatched_q = unpatched_q.where(PatchTitle.server_id == server_id)
    unpatched_result = await db.execute(unpatched_q)
    unpatched_count = unpatched_result.scalar_one() or 0

    total_smart_groups = await count(sg_q())
    total_servers = await count(select(JamfServer))
    active_servers = await count(select(JamfServer).where(JamfServer.is_active.is_(True)))

    os_dist_q = (
        select(Device.os_version, func.count().label("cnt"))
        .where(Device.os_version.isnot(None))
        .group_by(Device.os_version)
        .order_by(func.count().desc())
        .limit(10)
    )
    if server_id:
        os_dist_q = os_dist_q.where(Device.server_id == server_id)
    os_dist_result = await db.execute(os_dist_q)
    os_distribution = [OsVersionCount(os_version=row[0], count=row[1]) for row in os_dist_result]

    patch_sum_q = (
        select(PatchTitle.software_title, PatchTitle.patched_count, PatchTitle.unpatched_count)
        .order_by((PatchTitle.patched_count + PatchTitle.unpatched_count).desc())
        .limit(10)
    )
    if server_id:
        patch_sum_q = patch_sum_q.where(PatchTitle.server_id == server_id)
    patch_result = await db.execute(patch_sum_q)
    top_patches = [
        PatchSummary(software_title=row[0], patched=row[1], unpatched=row[2])
        for row in patch_result
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
