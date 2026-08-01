"""Pydantic schemas for smart groups."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SmartGroupResponse(BaseModel):
    id: uuid.UUID
    jamf_id: int
    name: str
    criteria: list[Any] | None
    member_count: int
    last_refreshed: datetime | None
    server_id: uuid.UUID
    server_url: str | None = None
    synced_at: datetime

    model_config = {"from_attributes": True}


class PagedSmartGroups(BaseModel):
    items: list[SmartGroupResponse]
    total: int
    page: int
    per_page: int
