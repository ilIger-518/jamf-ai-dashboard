"""Schemas for app users and roles."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.authz import ALL_PERMISSIONS, PERMISSION_LABELS


class PermissionOption(BaseModel):
    key: str
    label: str


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    permissions: list[str]
    is_system: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, permissions: list[str]) -> list[str]:
        invalid = [permission for permission in permissions if permission not in ALL_PERMISSIONS]
        if invalid:
            raise ValueError(f"Unknown permissions: {', '.join(sorted(invalid))}")
        return sorted(set(permissions))


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] | None = None

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, permissions: list[str] | None) -> list[str] | None:
        if permissions is None:
            return None
        invalid = [permission for permission in permissions if permission not in ALL_PERMISSIONS]
        if invalid:
            raise ValueError(f"Unknown permissions: {', '.join(sorted(invalid))}")
        return sorted(set(permissions))


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role_id: uuid.UUID
    is_active: bool = True

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not any(c.isupper() for c in value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one digit")
        return value


class UserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role_id: uuid.UUID | None = None
    is_active: bool | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not any(c.isupper() for c in value):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in value):
            raise ValueError("Password must contain at least one digit")
        return value


class UserAdminResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    role: RoleResponse | None
    permissions: list[str]


class PermissionsCatalogResponse(BaseModel):
    items: list[PermissionOption]


PERMISSIONS_CATALOG = [
    PermissionOption(key=key, label=PERMISSION_LABELS[key]) for key in ALL_PERMISSIONS
]
