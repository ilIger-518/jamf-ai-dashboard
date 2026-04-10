"""Schemas for package record synchronisation between Jamf Pro servers."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PackageSyncItem(BaseModel):
    id: int
    name: str
    filename: str | None = None
    category: str | None = None


class PackageSyncRequest(BaseModel):
    source_server_id: uuid.UUID
    target_server_ids: list[uuid.UUID] = Field(..., min_length=1)
    package_ids: list[int] = Field(..., min_length=1)
    skip_existing: bool = True
    transfer_file: bool = False

    @model_validator(mode="after")
    def validate_targets_differ(self) -> "PackageSyncRequest":
        if self.source_server_id in self.target_server_ids:
            raise ValueError("Source server cannot also be a target server")
        return self


class PackageSyncItemResult(BaseModel):
    package_id: int
    name: str
    status: Literal["created", "skipped", "failed"]
    message: str | None = None
    logs: list[str] = []
    file_status: Literal["transferred", "skipped", "failed"] | None = None
    file_message: str | None = None


class PackageSyncServerResult(BaseModel):
    target_server_id: uuid.UUID
    target_server_name: str
    created: int
    skipped: int
    failed: int
    results: list[PackageSyncItemResult]


class PackageSyncResponse(BaseModel):
    source_server_id: uuid.UUID
    servers: list[PackageSyncServerResult]
