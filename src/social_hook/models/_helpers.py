"""Shared datetime helpers for model serialization."""

from __future__ import annotations

from datetime import datetime


def _to_iso(dt: datetime | None) -> str | None:
    """Convert datetime to ISO string."""
    return dt.isoformat() if dt else None


def _from_iso(s: str | None) -> datetime | None:
    """Convert ISO string to datetime."""
    return datetime.fromisoformat(s) if s else None
