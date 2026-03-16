"""Schemas for dashboard audit logs."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


LogCategory = Literal["server", "login", "action"]


class DashboardLogResponse(BaseModel):
    id: uuid.UUID
    category: LogCategory
    action: str
    level: str
    message: str
    method: str | None = None
    path: str | None = None
    status_code: int | None = None
    user_id: uuid.UUID | None = None
    username: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
