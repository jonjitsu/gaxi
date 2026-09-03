"""Default unbound body properties from resolved path values."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi.jsonbody import body_properties
from gaxi.policy import IDENTIFIER_FIELDS

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.jsonshape import JsonObject, JsonValue

    CoerceFn = Callable[[JsonValue, str | None, str, Sequence[JsonValue] | None], JsonValue]


def apply_path_body_defaults(
    cap: Capability,
    binding: Binding,
    path_values: dict[str, str],
    coerce: CoerceFn,
) -> None:
    """Fill unbound body properties from resolved path values when names align."""
    declared = body_properties(cap)
    if not declared or not path_values:
        return
    if binding.is_batch():
        _apply_batch_path_body_defaults(cap, binding, path_values, declared, coerce)
        return
    _apply_single_path_body_defaults(cap, binding, path_values, declared, coerce)


def _apply_batch_path_body_defaults(
    cap: Capability,
    binding: Binding,
    path_values: dict[str, str],
    declared: JsonObject,
    coerce: CoerceFn,
) -> None:
    for body in binding.batch_bodies or []:
        if isinstance(body, dict):
            _fill_path_body_defaults(cap, body, path_values, declared, coerce)


def _apply_single_path_body_defaults(
    cap: Capability,
    binding: Binding,
    path_values: dict[str, str],
    declared: JsonObject,
    coerce: CoerceFn,
) -> None:
    if binding.body is None:
        materialized = _materialize_path_body_defaults(
            cap,
            path_values,
            declared,
            coerce,
        )
        if materialized:
            binding.body = materialized
        return
    if not isinstance(binding.body, dict):
        return
    _fill_path_body_defaults(cap, binding.body, path_values, declared, coerce)


def _materialize_path_body_defaults(
    cap: Capability,
    path_values: dict[str, str],
    declared: JsonObject,
    coerce: CoerceFn,
) -> dict[str, JsonValue]:
    body: dict[str, JsonValue] = {}
    _fill_path_body_defaults(cap, body, path_values, declared, coerce)
    return body


def _fill_path_body_defaults(
    cap: Capability,
    body: dict[str, JsonValue],
    path_values: dict[str, str],
    declared: JsonObject,
    coerce: CoerceFn,
) -> None:
    for name, schema in declared.items():
        if name in body or not _should_default_body_from_path(cap, name):
            continue
        raw = path_values.get(name)
        if raw is None:
            continue
        body[name] = coerce(raw, schema.get("type", "string"), name, schema.get("enum"))


def _path_param_names(cap: Capability) -> set[str]:
    return {param.name for param in cap.params_in("path")}


def _should_default_body_from_path(cap: Capability, name: str) -> bool:
    """Whether an unbound body property may inherit a same-named path value."""
    if name not in _path_param_names(cap):
        return False
    return name not in IDENTIFIER_FIELDS
