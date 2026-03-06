"""Pydantic schemas for devices."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class DeviceResponse(BaseModel):
    id: uuid.UUID
    jamf_id: int
    name: str
    serial_number: str | None
    model: str | None
    os_version: str | None
    is_managed: bool
    is_supervised: bool
    last_contact: datetime | None
    username: str | None
    full_name: str | None
    department: str | None
    building: str | None
    site: str | None
    server_id: uuid.UUID
    synced_at: datetime

    model_config = {"from_attributes": True}


class PagedDevices(BaseModel):
    items: list[DeviceResponse]
    total: int
    page: int
    per_page: int
