"""Compatibility helpers for datetime APIs across Python versions."""

from datetime import UTC, datetime, timedelta

UTC = UTC

__all__ = ["UTC", "datetime", "timedelta"]
