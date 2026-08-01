"""Pydantic schemas for patch management."""

import uuid
from datetime import datetime

from pydantic import BaseModel, computed_field


class PatchResponse(BaseModel):
    id: uuid.UUID
    jamf_id: int
    software_title: str
    current_version: str | None
    latest_version: str | None
    patched_count: int
    unpatched_count: int
    server_id: uuid.UUID
    server_url: str | None = None
    synced_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def total_count(self) -> int:
        return self.patched_count + self.unpatched_count

    @computed_field  # type: ignore[misc]
    @property
    def patch_percent(self) -> float:
        total = self.patched_count + self.unpatched_count
        if total == 0:
            return 0.0
        return round(self.patched_count / total * 100, 1)

    model_config = {"from_attributes": True}


class PagedPatches(BaseModel):
    items: list[PatchResponse]
    total: int
    page: int
    per_page: int
