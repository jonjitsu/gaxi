"""Resolve which response fields to project for one capability.

Precedence is fixed here so result shaping does not reach into policy and
projection separately:

1. explicit ``selected`` fields (--fields) after validation;
2. policy projection filtered to available response fields;
3. observed response fields ranked by policy fallback rules;
4. declared schema scalar names, capped at four.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi import projection
from gaxi.policy import (
    Properties,
    fallback_projection,
    schema_field_names,
    schema_property_names,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaxi.capability import Capability
    from gaxi.jsonshape import JsonValue

MAX_DECLARED_FIELDS = 4


def fields(
    cap: Capability,
    props: Properties,
    items: Sequence[JsonValue],
    selected: Sequence[str] | None,
) -> list[str]:
    """Choose the projection for one response using the documented precedence."""
    declared = schema_field_names(cap.success_response())
    if selected:
        projection.validate_fields(selected, items, declared)
        return list(selected)
    chosen = _policy_projection(
        props, items, declared, schema_property_names(cap.success_response()),
    )
    if chosen:
        return chosen
    observed = projection.observed_fields(items)
    if observed:
        return fallback_projection(observed)
    return declared[:MAX_DECLARED_FIELDS]


def _policy_projection(
    props: Properties,
    items: Sequence[JsonValue],
    declared: Sequence[str],
    schema_props: Sequence[str],
) -> list[str]:
    if not props.projection:
        return []
    available = set(projection.observed_fields(items)) | set(declared)
    schema_heads = set(schema_props)
    if not available and not schema_heads:
        return list(props.projection)
    return [
        field for field in props.projection
        if field.split(".")[0] in available
        or ("." in field and field.split(".")[0] in schema_heads)
    ]
