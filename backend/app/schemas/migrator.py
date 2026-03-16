"""Schemas for Jamf object migration between servers."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator

EntityType = Literal["policy", "smart_group", "static_group", "script"]


class MigratorObject(BaseModel):
    id: int
    name: str
    entity_type: EntityType


class ListMigratorObjectsResponse(BaseModel):
    items: list[MigratorObject]


class MigrationRequest(BaseModel):
    source_server_id: uuid.UUID
    target_server_id: uuid.UUID
    entity_type: EntityType
    object_ids: list[int] = Field(..., min_length=1)
    skip_existing: bool = True
    include_static_members: bool = False
    migrate_dependencies: bool = False

    @model_validator(mode="after")
    def validate_servers_differ(self) -> "MigrationRequest":
        if self.source_server_id == self.target_server_id:
            raise ValueError("Source and target server must be different")
        return self


class MigrationItemResult(BaseModel):
    object_id: int
    name: str
    status: Literal["created", "skipped", "failed"]
    message: str | None = None
    logs: list[str] = []


class MigrationResponse(BaseModel):
    entity_type: EntityType
    source_server_id: uuid.UUID
    target_server_id: uuid.UUID
    created: int
    skipped: int
    failed: int
    results: list[MigrationItemResult]
