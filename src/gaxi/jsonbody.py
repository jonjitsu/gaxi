"""Whole-body JSON validation.

`--input-json` supplies a complete body, so it is validated against the
capability's declared body schema before anything is sent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gaxi.errors import UsageError
from gaxi.suggestions import build, capability

if TYPE_CHECKING:
    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.jsonshape import JsonObject, JsonValue

@dataclass(frozen=True)
class InputJsonParse:
    """Bodies parsed from ``--input-json`` and whether the input was batch-shaped."""

    bodies: list[JsonValue]
    is_batch: bool


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
    return validate_json_value(cap, payload)


def validate_json_value(
    cap: Capability,
    payload: JsonValue,
    *,
    index: int | None = None,
    check_required: bool = True,
) -> JsonValue:
    """Validate one parsed JSON value against the capability's declared body schema."""
    properties = body_properties(cap)
    if not properties:
        return payload
    if not isinstance(payload, dict):
        label = f"--input-json element {index}" if index is not None else "--input-json"
        msg = f"{label} must be a JSON object for this capability"
        raise UsageError(msg, details=[("capability", cap.key)])
    if body_schema(cap).get("additionalProperties") is not True:
        _reject_unknown(cap, payload, properties)
    _check_property_types(cap, payload, properties)
    if check_required:
        _check_required_properties(cap, payload, properties, index=index)
    return payload


def validate_binding_body_required(cap: Capability, binding: Binding) -> None:
    """Validate required body properties on the bound body after path defaults."""
    properties = body_properties(cap)
    if not properties:
        return
    if binding.is_batch() and binding.batch_bodies is not None:
        for index, body in enumerate(binding.batch_bodies):
            if isinstance(body, dict):
                _check_required_properties(cap, body, properties, index=index)
        return
    if isinstance(binding.body, dict):
        _check_required_properties(cap, binding.body, properties)


def parse_input_json_bodies(
    cap: Capability,
    text: str,
    *,
    check_required: bool = True,
) -> InputJsonParse:
    """Parse `--input-json` as one body or a batch of bodies.

    A JSON array supplies multiple bodies and preserves batch shape even when it
    contains one element. When the whole text is not valid JSON, each non-empty
    line is parsed as NDJSON.
    """
    stripped = text.strip()
    if not stripped:
        msg = "--input-json is empty"
        raise UsageError(msg)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return InputJsonParse(
            _parse_ndjson_bodies(cap, text, check_required=check_required),
            is_batch=True,
        )
    if isinstance(payload, list):
        return InputJsonParse(
            [
                validate_json_value(cap, item, index=index, check_required=check_required)
                for index, item in enumerate(payload)
            ],
            is_batch=True,
        )
    return InputJsonParse(
        [validate_json_value(cap, payload, check_required=check_required)],
        is_batch=False,
    )


def _parse_ndjson_bodies(
    cap: Capability,
    text: str,
    *,
    check_required: bool = True,
) -> list[JsonValue]:
    """Parse one JSON object per non-empty line."""
    bodies: list[JsonValue] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            msg = f"--input-json line {line_number} is not valid JSON: {exc.msg}"
            raise UsageError(
                msg,
                details=[("line", str(line_number)), ("position", str(exc.pos))],
            ) from exc
        bodies.append(
            validate_json_value(
                cap,
                payload,
                index=len(bodies),
                check_required=check_required,
            ),
        )
    return bodies


def _check_required_properties(
    cap: Capability,
    payload: JsonObject,
    properties: JsonObject,
    *,
    index: int | None = None,
) -> None:
    """Refuse a body object that omits a required property."""
    missing = [
        name
        for name in body_schema(cap).get("required") or []
        if name in properties and name not in payload
    ]
    if not missing:
        return
    label = f"--input-json element {index}" if index is not None else "--input-json"
    msg = f"{label} is missing required body property {missing[0]}"
    raise UsageError(
        msg,
        details=[("missing", ", ".join(missing)), ("capability", cap.key)],
        help_commands=build(capability(cap.key)),
    )


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
