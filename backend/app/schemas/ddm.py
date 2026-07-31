"""Pydantic schemas for DDM (Declarative Device Management)."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DDMDeviceListItem(BaseModel):
    """Lightweight device row shown in the DDM device list."""

    id: uuid.UUID
    jamf_id: int
    name: str
    serial_number:Optional[str]
    model:Optional[str]
    os_version:Optional[str]
    username:Optional[str]
    department:Optional[str]
    last_contact:Optional[datetime]
    management_id:Optional[str]
    server_id: uuid.UUID

    model_config = {"from_attributes": True}


class PagedDDMDevices(BaseModel):
    items: list[DDMDeviceListItem]
    total: int
    page: int
    per_page: int


class DDMStatusItem(BaseModel):
    """A single DDM status-item entry returned by the Jamf Pro API."""

    identifier: str
    valid:Optional[str] = None
    reasons:Optional[list[dict]] = None
    client:Optional[dict] = None


class DDMStatusResponse(BaseModel):
    """Live DDM status fetched from Jamf Pro for a single device."""

    device_id: uuid.UUID
    management_id: str
    status_items: list[dict]
    raw: dict


class DDMSyncResponse(BaseModel):
    """Result of triggering a DDM force-sync on a device."""

    device_id: uuid.UUID
    management_id: str
    message: str
from typing import Optional