"""Pydantic schemas for policies."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class PolicyResponse(BaseModel):
    id: uuid.UUID
    jamf_id: int
    name: str
    enabled: bool
    category: str | None
    trigger: str | None
    scope_description: str | None
    server_id: uuid.UUID
    server_url: str | None = None
    synced_at: datetime

    model_config = {"from_attributes": True}


class PagedPolicies(BaseModel):
    items: list[PolicyResponse]
    total: int
    page: int
    per_page: int
