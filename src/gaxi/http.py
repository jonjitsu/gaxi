"""Shared HTTP status vocabulary and small parsing helpers."""

from __future__ import annotations

FIRST_SUCCESS = 200
FIRST_REDIRECT = 300
FIRST_FAILURE = 400
NOT_MODIFIED = 304


def parse_int(value: str | None) -> int | None:
    """Parse an integer assignment, or None when absent or invalid."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
