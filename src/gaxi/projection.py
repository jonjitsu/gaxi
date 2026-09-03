"""Projections and the truncation contract.

Projected field names stay faithful to the instance response. Every projected
string is limited to 160 Unicode characters, applied after projection and before
output encoding.
"""

from __future__ import annotations

import difflib
import json
from typing import TYPE_CHECKING

from gaxi.errors import UsageError

# Response-name pairs only — not planner path-param aliases (login→assignee, etc.).
PROJECT_FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "index": ("index", "number"),
    "number": ("number", "index"),
    "login": ("login", "username"),
    "username": ("username", "login"),
}

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from gaxi.jsonshape import JsonValue

LIMIT = 160
KNOWN_FIELDS_SHOWN = 12
DID_YOU_MEAN_CUTOFF = 0.75
DID_YOU_MEAN_MARGIN = 0.15
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


def omitted_fields(
    items: Sequence[JsonValue],
    projection: Sequence[str],
) -> list[str]:
    """Top-level response fields present in items but not covered by the projection."""
    projected_heads = {_field_head(field) for field in projection}
    return [
        name
        for name in observed_fields(items)
        if name not in projected_heads
    ]


def _field_head(field: str) -> str:
    return field.split(".", maxsplit=1)[0]


def _field_closeness(requested: str, candidate: str) -> float:
    head = _field_head(requested)
    if candidate in PROJECT_FIELD_SYNONYMS.get(head, ()):
        return 1.0
    return difflib.SequenceMatcher(None, head, candidate).ratio()


def _rank_known_fields(requested: str, known: set[str]) -> list[str]:
    return sorted(known, key=lambda name: (-_field_closeness(requested, name), name))


def _did_you_mean(requested: str, known: set[str]) -> str | None:
    head = _field_head(requested)
    for synonym in PROJECT_FIELD_SYNONYMS.get(head, ()):
        if synonym != head and synonym in known:
            return synonym
    ranked = sorted(known, key=lambda name: _field_closeness(requested, name), reverse=True)
    if not ranked:
        return None
    best = ranked[0]
    best_score = _field_closeness(requested, best)
    if best_score < DID_YOU_MEAN_CUTOFF:
        return None
    if len(ranked) > 1:
        second_score = _field_closeness(requested, ranked[1])
        if best_score - second_score < DID_YOU_MEAN_MARGIN:
            return None
    return best


def _unknown_field_details(field: str, known: set[str]) -> list[tuple[str, str]]:
    ranked = _rank_known_fields(field, known)
    details: list[tuple[str, str]] = [
        ("field", field),
        ("known", ", ".join(ranked[:KNOWN_FIELDS_SHOWN]) or "none observed"),
    ]
    if suggestion := _did_you_mean(field, known):
        details.append(("did_you_mean", suggestion))
    return details


def validate_fields(
    fields: Iterable[str],
    items: Sequence[JsonValue],
    declared: Iterable[str] = (),
) -> None:
    """Reject a selected field the advertised or observed response does not have."""
    known = set(declared) | set(observed_fields(items))
    for field in fields:
        head = _field_head(field)
        if head in known:
            continue
        if any(resolve_path(item, field) is not MISSING for item in items):
            continue
        msg = f"no response field named {field}"
        raise UsageError(msg, details=_unknown_field_details(field, known))


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
