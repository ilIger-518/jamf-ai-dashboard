"""Dashboard statistics router."""

from fastapi import APIRouter
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
async def get_stats(db: DBSession, _: CurrentUser) -> DashboardStats:
    async def count(q) -> int:  # type: ignore[type-arg]
        r = await db.execute(select(func.count()).select_from(q.subquery()))
        return r.scalar_one()

    total_devices = await count(select(Device))
    managed_devices = await count(select(Device).where(Device.is_managed.is_(True)))
    total_policies = await count(select(Policy))
    enabled_policies = await count(select(Policy).where(Policy.enabled.is_(True)))
    total_patches = await count(select(PatchTitle))

    unpatched_result = await db.execute(select(func.sum(PatchTitle.unpatched_count)))
    unpatched_count = unpatched_result.scalar_one() or 0

    total_smart_groups = await count(select(SmartGroup))
    total_servers = await count(select(JamfServer))
    active_servers = await count(select(JamfServer).where(JamfServer.is_active.is_(True)))

    os_dist_result = await db.execute(
        select(Device.os_version, func.count().label("cnt"))
        .where(Device.os_version.isnot(None))
        .group_by(Device.os_version)
        .order_by(func.count().desc())
        .limit(10)
    )
    os_distribution = [
        OsVersionCount(os_version=row[0], count=row[1]) for row in os_dist_result
    ]

    patch_result = await db.execute(
        select(PatchTitle.software_title, PatchTitle.patched_count, PatchTitle.unpatched_count)
        .order_by((PatchTitle.patched_count + PatchTitle.unpatched_count).desc())
        .limit(10)
    )
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
