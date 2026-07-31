"""Schemas for dashboard audit logs."""

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

LogCategory = Literal["server", "login", "action"]


class DashboardLogResponse(BaseModel):
    id: uuid.UUID
    category: LogCategory
    action: str
    level: str
    message: str
    method:Optional[str] = None
    path:Optional[str] = None
    status_code:Optional[int] = None
    user_id:Optional[uuid.UUID] = None
    username:Optional[str] = None
    ip_address:Optional[str] = None
    user_agent:Optional[str] = None
    details:Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}
