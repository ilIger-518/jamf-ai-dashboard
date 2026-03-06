"""Dashboard statistics router."""

from fastapi import APIRouter
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession
from app.models.device import Device
from app.models.patch import PatchTitle
from app.models.policy import Policy
from app.models.server import JamfServer
from app.models.smart_group import SmartGroup
from app.schemas.dashboard import DashboardStats

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
    )
