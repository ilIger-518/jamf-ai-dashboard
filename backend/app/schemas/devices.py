"""Pydantic schemas for devices."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DeviceResponse(BaseModel):
    id: uuid.UUID
    jamf_id: int
    name: str
    serial_number:Optional[str]
    asset_tag:Optional[str]
    model:Optional[str]
    model_identifier:Optional[str]
    processor:Optional[str]
    ram_mb:Optional[int]
    os_version:Optional[str]
    os_build:Optional[str]
    is_managed: bool
    is_supervised: bool
    last_contact:Optional[datetime]
    last_enrollment:Optional[datetime]
    username:Optional[str]
    full_name:Optional[str]
    email:Optional[str]
    department:Optional[str]
    building:Optional[str]
    site:Optional[str]
    server_id: uuid.UUID
    server_url:Optional[str] = None
    synced_at: datetime

    model_config = {"from_attributes": True}


class PagedDevices(BaseModel):
    items: list[DeviceResponse]
    total: int
    page: int
    per_page: int
from typing import Optional