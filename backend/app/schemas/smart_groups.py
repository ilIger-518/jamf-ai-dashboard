"""Pydantic schemas for smart groups."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SmartGroupResponse(BaseModel):
    id: uuid.UUID
    jamf_id: int
    name: str
    criteria:Optional[list[Any]]
    member_count: int
    last_refreshed:Optional[datetime]
    server_id: uuid.UUID
    server_url:Optional[str] = None
    synced_at: datetime

    model_config = {"from_attributes": True}


class PagedSmartGroups(BaseModel):
    items: list[SmartGroupResponse]
    total: int
    page: int
    per_page: int
