"""Projections and the truncation contract.

Projected field names stay faithful to the instance response. Every projected
string is limited to 160 Unicode characters, applied after projection and before
output encoding.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gaxi.errors import UsageError

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from gaxi.jsonshape import JsonValue

LIMIT = 160
KNOWN_FIELDS_SHOWN = 12
ELLIPSIS = "…"
MISSING = object()


def resolve_path(value: JsonValue, path: str) -> JsonValue:
    """Resolve a dotted path against a response value."""
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return MISSING
    return current


def cell_value(value: JsonValue) -> str | int | float | bool | None:
    """Flatten one projected value to a scalar the encoders can render."""
    if value is MISSING or value is None:
        return None
    if isinstance(value, str | int | float | bool):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def truncate(value: JsonValue, *, full: bool = False) -> tuple[JsonValue, int | None]:
    """Apply the truncation contract; returns `(value, original_length)`."""
    if full or not isinstance(value, str):
        return value, None
    if len(value) <= LIMIT:
        return value, None
    return value[: LIMIT - 1] + ELLIPSIS, len(value)


def observed_fields(items: Iterable[JsonValue]) -> list[str]:
    """Top-level field names observed in a response, in first-seen order."""
    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for name in item:
            if name not in names:
                names.append(name)
    return names


def validate_fields(
    fields: Iterable[str],
    items: Sequence[JsonValue],
    declared: Iterable[str] = (),
) -> None:
    """Reject a selected field the advertised or observed response does not have."""
    known = set(declared) | set(observed_fields(items))
    for field in fields:
        head = field.split(".")[0]
        if head in known:
            continue
        if any(resolve_path(item, field) is not MISSING for item in items):
            continue
        msg = f"no response field named {field}"
        raise UsageError(
            msg,
            details=[
                ("field", field),
                ("known", ", ".join(sorted(known)[:KNOWN_FIELDS_SHOWN]) or "none observed"),
            ],
        )


def project_rows(
    items: Iterable[JsonValue],
    fields: Sequence[str],
    *,
    full: bool = False,
) -> tuple[list[list[tuple[JsonValue, bool]]], list[tuple[int, str, int]]]:
    """Project a collection; returns `(rows, truncations)`."""
    rows: list[list[tuple[JsonValue, bool]]] = []
    truncations: list[tuple[int, str, int]] = []
    for index, item in enumerate(items, start=1):
        row: list[tuple[JsonValue, bool]] = []
        for field in fields:
            value = cell_value(resolve_path(item, field))
            shortened, original = truncate(value, full=full)
            if original is not None:
                truncations.append((index, field, original))
            row.append((shortened, original is not None))
        rows.append(row)
    return rows, truncations


def project_object(
    value: JsonValue,
    fields: Iterable[str],
    *,
    full: bool = False,
) -> tuple[list[tuple[str, JsonValue, bool]], list[tuple[str, int]]]:
    """Project a detail object; returns `(pairs, truncations)`."""
    pairs: list[tuple[str, JsonValue, bool]] = []
    truncations: list[tuple[str, int]] = []
    for field in fields:
        cell = cell_value(resolve_path(value, field))
        shortened, original = truncate(cell, full=full)
        if original is not None:
            truncations.append((field, original))
        pairs.append((field, shortened, original is not None))
    return pairs, truncations
