"""Pydantic schemas for Jamf server management."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Privilege presets
# ---------------------------------------------------------------------------

READONLY_PRIVILEGES: list[str] = [
    "Read Computers",
    "Read Computer Inventory Collection",
    "Read Smart Computer Groups",
    "Read Static Computer Groups",
    "Read Mobile Devices",
    "Read Mobile Device Inventory Collection",
    "Read Smart Mobile Device Groups",
    "Read Static Mobile Device Groups",
    "Read Policies",
    "Read Categories",
    "Read Departments",
    "Read Buildings",
    "Read Sites",
    "Read Scripts",
    "Read Computer Extension Attributes",
    "Read Mobile Device Extension Attributes",
    "Read Patch Management Software Titles",
    "Read Patch Policies",
    "Read Advanced Computer Searches",
]

FULL_PRIVILEGES: list[str] = READONLY_PRIVILEGES + [
    "Create Computers",
    "Update Computers",
    "Delete Computers",
    "Create Policies",
    "Update Policies",
    "Delete Policies",
    "Create Smart Computer Groups",
    "Update Smart Computer Groups",
    "Delete Smart Computer Groups",
    "Create Static Computer Groups",
    "Update Static Computer Groups",
    "Delete Static Computer Groups",
    "Create Smart Mobile Device Groups",
    "Update Smart Mobile Device Groups",
    "Delete Smart Mobile Device Groups",
    "Create Scripts",
    "Update Scripts",
    "Delete Scripts",
    "Create Computer Extension Attributes",
    "Update Computer Extension Attributes",
    "Delete Computer Extension Attributes",
    "Send Computer Remote Lock Command",
    "Send Computer Remote Wipe Command",
]


# ---------------------------------------------------------------------------
# Provision wizard
# ---------------------------------------------------------------------------


class ServerProvision(BaseModel):
    """Input for the auto-provisioning wizard."""

    server_name: str = Field(..., min_length=1, max_length=128)
    jamf_url: str = Field(..., min_length=1, max_length=512)
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    preset: Literal["readonly", "full"] = "full"


class ProvisionedCredentials(BaseModel):
    role_name: str
    client_id: str
    client_secret: str


# ---------------------------------------------------------------------------
# Standard CRUD schemas
# ---------------------------------------------------------------------------


class ServerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    url: str = Field(..., min_length=1, max_length=512)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    ai_client_id: str | None = None
    ai_client_secret: str | None = None


class ServerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    ai_client_id: str | None = None
    ai_client_secret: str | None = None
    is_active: bool | None = None


class ServerResponse(BaseModel):
    id: uuid.UUID
    name: str
    url: str
    is_active: bool
    last_sync: datetime | None
    last_sync_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProvisionResult(BaseModel):
    """Returned after successful provisioning — contains the saved server plus
    the generated credential names so the user can verify in Jamf Pro."""

    server: ServerResponse
    admin_role: str
    admin_client_display_name: str
    readonly_role: str
    readonly_client_display_name: str
