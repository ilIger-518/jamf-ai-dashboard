"""Pydantic schemas for Jamf server management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Privilege presets
# ---------------------------------------------------------------------------

READONLY_PRIVILEGES: list[str] = [
    "Read Computers",
    "Read Computer Inventory Collection",
    "Read Computer Management",
    "Read Computer Groups",
    "Read Computer Reports",
    "Read Mobile Devices",
    "Read Mobile Device Inventory Collection",
    "Read Mobile Device Groups",
    "Read Mobile Device Management",
    "Read Users",
    "Read User Groups",
    "Read Policies",
    "Read Categories",
    "Read Departments",
    "Read Buildings",
    "Read Sites",
    "Read Scripts",
    "Read Extension Attributes",
    "Read Computer Extension Attributes",
    "Read Mobile Device Extension Attributes",
    "Read Patch Management Software Titles",
    "Read Patch Policies",
    "Read Smart Computer Groups",
    "Read Smart Mobile Device Groups",
    "Read Advanced Computer Searches",
]

FULL_PRIVILEGES: list[str] = READONLY_PRIVILEGES + [
    "Create Computers",
    "Update Computers",
    "Delete Computers",
    "Create Policies",
    "Update Policies",
    "Delete Policies",
    "Create Computer Groups",
    "Update Computer Groups",
    "Delete Computer Groups",
    "Create Mobile Device Groups",
    "Update Mobile Device Groups",
    "Delete Mobile Device Groups",
    "Create Scripts",
    "Update Scripts",
    "Delete Scripts",
    "Create Computer Extension Attributes",
    "Update Computer Extension Attributes",
    "Delete Computer Extension Attributes",
    "Send Computer Remote Lock Command",
    "Send Computer Remote Wipe Command",
    "Send Computer Unmanage Command",
    "Update Computer Management",
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
