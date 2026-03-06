"""Pydantic schemas for Jamf server management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
