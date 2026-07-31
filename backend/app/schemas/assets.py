"""Schemas for live Jamf script/package catalog endpoints."""

from typing import Optional

from pydantic import BaseModel


class ScriptItem(BaseModel):
    id: int
    name: str
    category:Optional[str] = None
    jamf_script_url: str


class ScriptParameter(BaseModel):
    index: int
    label: str
    value: str


class ScriptDetailItem(BaseModel):
    id: int
    name: str
    category:Optional[str] = None
    notes:Optional[str] = None
    info:Optional[str] = None
    priority:Optional[str] = None
    os_requirements:Optional[str] = None
    script_contents: str
    parameters: list[ScriptParameter] = []
    jamf_script_url: str


class PackageItem(BaseModel):
    id: int
    name: str
    filename:Optional[str] = None
    category:Optional[str] = None
from typing import Optional