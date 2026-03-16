"""Helpers for writing dashboard audit logs."""

from __future__ import annotations

import uuid

from app.database import AsyncSessionLocal
from app.models.dashboard_log import DashboardLog


async def write_dashboard_log(
    *,
    category: str,
    action: str,
    message: str,
    level: str = "info",
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    user_id: uuid.UUID | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict | None = None,
) -> None:
    """Persist a dashboard log entry.

    This helper is intentionally best-effort and should never break request handling.
    """

    try:
        async with AsyncSessionLocal() as db:
            db.add(
                DashboardLog(
                    category=category,
                    action=action,
                    level=level,
                    message=message,
                    method=method,
                    path=path,
                    status_code=status_code,
                    user_id=user_id,
                    username=username,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=details,
                )
            )
            await db.commit()
    except Exception:
        # Intentionally ignore logging failures.
        return
