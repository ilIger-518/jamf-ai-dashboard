"""Pydantic schemas for DDM (Declarative Device Management)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class DDMDeviceListItem(BaseModel):
    """Lightweight device row shown in the DDM device list."""

    id: uuid.UUID
    jamf_id: int
    name: str
    serial_number: str | None
    model: str | None
    os_version: str | None
    username: str | None
    department: str | None
    last_contact: datetime | None
    management_id: str | None
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
    valid: str | None = None
    reasons: list[dict] | None = None
    client: dict | None = None


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
