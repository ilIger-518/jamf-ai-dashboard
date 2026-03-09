"""Pydantic schemas for dashboard statistics."""

from pydantic import BaseModel


class OsVersionCount(BaseModel):
    os_version: str
    count: int


class PatchSummary(BaseModel):
    software_title: str
    patched: int
    unpatched: int


class DashboardStats(BaseModel):
    total_devices: int
    managed_devices: int
    total_policies: int
    enabled_policies: int
    total_patches: int
    unpatched_count: int
    total_smart_groups: int
    total_servers: int
    active_servers: int
    os_distribution: list[OsVersionCount]
    top_patches: list[PatchSummary]
