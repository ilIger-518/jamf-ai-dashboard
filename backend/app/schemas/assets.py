"""Schemas for live Jamf script/package catalog endpoints."""

from pydantic import BaseModel


class ScriptItem(BaseModel):
    id: int
    name: str
    category: str | None = None
    jamf_script_url: str


class ScriptParameter(BaseModel):
    index: int
    label: str
    value: str


class ScriptDetailItem(BaseModel):
    id: int
    name: str
    category: str | None = None
    notes: str | None = None
    info: str | None = None
    priority: str | None = None
    os_requirements: str | None = None
    script_contents: str
    parameters: list[ScriptParameter] = []
    jamf_script_url: str


class PackageItem(BaseModel):
    id: int
    name: str
    filename: str | None = None
    category: str | None = None
