"""Schemas for live Jamf script/package catalog endpoints."""

from pydantic import BaseModel


class ScriptItem(BaseModel):
    id: int
    name: str
    category: str | None = None


class PackageItem(BaseModel):
    id: int
    name: str
    filename: str | None = None
    category: str | None = None
