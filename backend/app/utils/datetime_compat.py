"""Compatibility helpers for datetime APIs across Python versions."""

from datetime import datetime, timedelta, timezone

UTC = timezone.utc

__all__ = ["UTC", "datetime", "timedelta"]
