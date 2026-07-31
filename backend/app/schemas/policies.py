"""Pydantic schemas for policies."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PolicyResponse(BaseModel):
    id: uuid.UUID
    jamf_id: int
    name: str
    enabled: bool
    category:Optional[str]
    trigger:Optional[str]
    scope_description:Optional[str]
    server_id: uuid.UUID
    server_url:Optional[str] = None
    synced_at: datetime

    model_config = {"from_attributes": True}


class PagedPolicies(BaseModel):
    items: list[PolicyResponse]
    total: int
    page: int
    per_page: int
from typing import Optional