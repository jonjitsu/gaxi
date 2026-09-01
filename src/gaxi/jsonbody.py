"""Whole-body JSON validation.

`--input-json` supplies a complete body, so it is validated against the
capability's declared body schema before anything is sent.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gaxi.errors import UsageError
from gaxi.suggestions import build, capability

if TYPE_CHECKING:
    from gaxi.capability import Capability
    from gaxi.jsonshape import JsonObject, JsonValue

JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def body_schema(cap: Capability) -> JsonObject:
    """The capability's declared body schema, or an empty schema."""
    if cap.body is None or not cap.body.schema:
        return {}
    return cap.body.schema


def body_properties(cap: Capability) -> JsonObject:
    """The declared body properties, or nothing when the body is not an object."""
    schema = body_schema(cap)
    if schema.get("type") not in (None, "object"):
        return {}
    properties: JsonObject = schema.get("properties") or {}
    return properties


def validate_json_body(cap: Capability, text: str) -> JsonValue:
    """Validate a complete JSON body against the capability's declared schema."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"--input-json is not valid JSON: {exc.msg}"
        raise UsageError(msg, details=[("position", str(exc.pos))]) from exc
    properties = body_properties(cap)
    if not properties:
        return payload
    if not isinstance(payload, dict):
        msg = "--input-json must be a JSON object for this capability"
        raise UsageError(msg, details=[("capability", cap.key)])
    if body_schema(cap).get("additionalProperties") is not True:
        _reject_unknown(cap, payload, properties)
    _check_property_types(cap, payload, properties)
    return payload


def _reject_unknown(cap: Capability, payload: JsonObject, properties: JsonObject) -> None:
    """Refuse a body property the capability does not declare."""
    unknown = sorted(set(payload) - set(properties))
    if not unknown:
        return
    msg = f"{cap.key} declares no body property named {unknown[0]}"
    raise UsageError(
        msg,
        details=[("unknown", ", ".join(unknown)), ("capability", cap.key)],
        help_commands=build(capability(cap.key)),
    )


def _check_property_types(cap: Capability, payload: JsonObject, properties: JsonObject) -> None:
    """Refuse a body property whose JSON type contradicts the declared schema."""
    for name, value in payload.items():
        expected = (properties.get(name) or {}).get("type")
        if expected and not _json_type_matches(expected, value):
            msg = f"{name} expects {expected}, got {type(value).__name__}"
            raise UsageError(msg, details=[("input", name), ("capability", cap.key)])


def _json_type_matches(expected: str, value: JsonValue) -> bool:
    types = JSON_TYPES.get(expected)
    if types is None:
        return True
    if expected in {"integer", "number"} and isinstance(value, bool):
        return False
    return isinstance(value, types)
