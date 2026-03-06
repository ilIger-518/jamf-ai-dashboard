"""Pydantic schemas for dashboard statistics."""

from pydantic import BaseModel


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
