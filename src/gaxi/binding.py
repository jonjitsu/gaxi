"""Schema-routed input binding.

API inputs are `name=value` arguments routed to the query, body, or form input
declared by the resolved capability. Every rejection happens before a request is
sent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode

from gaxi.errors import UsageError
from gaxi.jsonbody import body_properties, body_schema, validate_json_body
from gaxi.suggestions import build, capability

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from gaxi.capability import Capability, Param
    from gaxi.jsonshape import JsonValue

QUALIFIERS = {"query": "query", "body": "body", "form": "formData"}
QUALIFIERS_INVERSE = {"query": "query", "body": "body", "formData": "form"}
DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20

type Assignment = tuple[str | None, str, str, str]


class Binding:
    """Bound and validated inputs for one invocation."""

    def __init__(self) -> None:
        self.query: list[tuple[str, str]] = []
        self.body: JsonValue = None
        self.form: list[tuple[str, str]] = []
        self.files: list[tuple[str, str]] = []
        self.defaults: list[tuple[str, JsonValue]] = []
        self.body_is_raw = False

    def query_string(self) -> str:
        """The bound query inputs, encoded."""
        return urlencode(self.query, doseq=False)

    def describe(self) -> list[tuple[str, str]]:
        """Every bound input, labelled by where it will be sent."""
        pairs = [(f"query:{name}", value) for name, value in self.query]
        pairs += [(f"form:{name}", value) for name, value in self.form]
        pairs += [(f"file:{name}", path) for name, path in self.files]
        if self.body is not None:
            pairs.append(("body", json.dumps(self.body, sort_keys=True)))
        return pairs


@dataclass
class _BodyState:
    """Body inputs accumulated while binding one invocation."""

    scalars: dict[str, JsonValue] = field(default_factory=dict)
    arrays: dict[str, list[JsonValue]] = field(default_factory=dict)
    supplied: list[str] = field(default_factory=list)
    seen: set[tuple[str, str]] = field(default_factory=set)


def split_assignment(argument: str) -> tuple[str, str]:
    """Split one `name=value` assignment, rejecting anything else."""
    name, separator, value = argument.partition("=")
    if not separator:
        msg = f"expected an input assignment name=value, got {argument!r}"
        raise UsageError(msg, details=[("argument", argument)])
    return name, value


def _locations(cap: Capability, name: str) -> list[str]:
    found = []
    if any(p.name == name for p in cap.params_in("query")):
        found.append("query")
    if name in body_properties(cap):
        found.append("body")
    if any(p.name == name for p in cap.params_in("formData")):
        found.append("formData")
    return found


def _param(cap: Capability, location: str, name: str) -> Param | None:
    for param in cap.params_in(location):
        if param.name == name:
            return param
    return None


def _coerce(
    value: JsonValue,
    type_: str | None,
    name: str,
    enum: Sequence[JsonValue] | None = None,
) -> JsonValue:
    coerced = _coerce_scalar(value, type_, name)
    if enum and str(coerced) not in [str(item) for item in enum]:
        msg = f"{name} expects one of {', '.join(str(item) for item in enum)}"
        raise UsageError(msg, details=[("input", name), ("value", str(value))])
    return coerced


def _rejected(name: str, value: JsonValue, expected: str) -> UsageError:
    msg = f"{name} expects {expected}, got {value!r}"
    return UsageError(msg, details=[("input", name), ("value", str(value))])


def _coerce_number(value: JsonValue, type_: str, name: str) -> JsonValue:
    converter = int if type_ == "integer" else float
    try:
        return converter(value)
    except (TypeError, ValueError) as exc:
        expected = "an integer" if type_ == "integer" else "a number"
        raise _rejected(name, value, expected) from exc


def _coerce_boolean(value: JsonValue, name: str) -> bool:
    lowered = str(value).lower()
    if lowered not in {"true", "false"}:
        raise _rejected(name, value, "true or false")
    return lowered == "true"


def _coerce_scalar(value: JsonValue, type_: str | None, name: str) -> JsonValue:
    if type_ in {"integer", "number"}:
        return _coerce_number(value, str(type_), name)
    if type_ == "boolean":
        return _coerce_boolean(value, name)
    return value


def _as_query_text(value: JsonValue) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _parse_assignments(assignments: Iterable[str], path_query: str) -> list[Assignment]:
    parsed: list[Assignment] = [
        ("query", name, value, "path query")
        for name, value in parse_qsl(path_query, keep_blank_values=True)
    ]
    for argument in assignments:
        raw_name, value = split_assignment(argument)
        qualifier, separator, name = raw_name.partition(":")
        if separator and qualifier in QUALIFIERS:
            parsed.append((QUALIFIERS[qualifier], name, value, "assignment"))
        elif separator:
            msg = f"unknown input qualifier {qualifier!r} in {raw_name!r}"
            raise UsageError(
                msg,
                details=[
                    ("argument", argument),
                    ("expected", "query:, body:, or form:"),
                ],
            )
        else:
            parsed.append((None, raw_name, value, "assignment"))
    return parsed


def _resolve_location(cap: Capability, location: str | None, name: str) -> str:
    if location is None:
        return _infer_location(cap, name)
    declared = name in body_properties(cap) if location == "body" else (
        _param(cap, location, name) is not None
    )
    if not declared:
        label = "body property" if location == "body" else f"{QUALIFIERS_INVERSE[location]} input"
        msg = f"{cap.key} declares no {label} named {name}"
        raise UsageError(
            msg,
            details=[("input", name), ("capability", cap.key)],
            help_commands=build(capability(cap.key)),
        )
    return location


def _infer_location(cap: Capability, name: str) -> str:
    candidates = _locations(cap, name)
    if not candidates:
        msg = f"{cap.key} declares no input named {name}"
        raise UsageError(
            msg,
            details=[("input", name), ("capability", cap.key)],
            help_commands=build(capability(cap.key)),
        )
    if len(candidates) > 1:
        qualified = ", ".join(f"{QUALIFIERS_INVERSE[c]}:{name}=" for c in candidates)
        msg = f"{name} is declared in {len(candidates)} locations"
        raise UsageError(msg, details=[("input", name), ("qualify_with", qualified)])
    return candidates[0]


def _bind_body_input(
    cap: Capability,
    state: _BodyState,
    assignment: tuple[str, str, str],
) -> None:
    name, value, source = assignment
    schema = body_properties(cap)[name]
    state.supplied.append(name)
    if schema.get("type") == "array":
        items = schema.get("items") or {}
        state.arrays.setdefault(name, []).append(
            _coerce(value, items.get("type", "string"), name, items.get("enum")),
        )
        return
    _reject_duplicate(state.seen, "body", name, source)
    state.scalars[name] = _coerce(value, schema.get("type", "string"), name, schema.get("enum"))


def _bind_file_input(binding: Binding, name: str, value: str) -> None:
    if not value.startswith("@"):
        msg = f"{name} is a file input; supply it as {name}=@path"
        raise UsageError(msg, details=[("input", name), ("value", value)])
    path = value.removeprefix("@")
    if not Path(path).is_file():
        msg = f"no such file: {path}"
        raise UsageError(msg, details=[("input", name), ("path", path)])
    binding.files.append((name, path))


def _bind_param_input(
    cap: Capability,
    binding: Binding,
    state: _BodyState,
    location: str,
    assignment: tuple[str, str, str],
) -> None:
    name, value, source = assignment
    param = _param(cap, location, name)
    if param is None:  # pragma: no cover - _resolve_location already proved it exists
        msg = f"{cap.key} declares no input named {name}"
        raise UsageError(msg, details=[("input", name), ("capability", cap.key)])
    if param.is_file:
        _bind_file_input(binding, name, value)
        return
    if param.is_array:
        coerced = _coerce(value, param.items_type or "string", name, param.items_enum)
    else:
        _reject_duplicate(state.seen, location, name, source)
        coerced = _coerce(value, param.type or "string", name, param.enum)
    target = binding.query if location == "query" else binding.form
    target.append((name, _as_query_text(coerced)))


def bind(
    cap: Capability,
    assignments: Iterable[str],
    path_query: str = "",
    input_json: str | None = None,
    *,
    apply_pagination: bool = True,
) -> Binding:
    """Bind caller assignments to the resolved capability's declared inputs."""
    binding = Binding()
    state = _BodyState()

    for location, name, value, source in _parse_assignments(assignments, path_query):
        resolved = _resolve_location(cap, location, name)
        if resolved == "body":
            _bind_body_input(cap, state, (name, value, source))
        else:
            _bind_param_input(cap, binding, state, resolved, (name, value, source))

    _attach_body(cap, binding, state, input_json)
    _check_required(cap, binding, state.supplied)
    if apply_pagination:
        _apply_pagination(cap, binding)
    return binding


def _attach_body(
    cap: Capability,
    binding: Binding,
    state: _BodyState,
    input_json: str | None,
) -> None:
    """Attach either the whole supplied body or the assembled body assignments."""
    if input_json is not None:
        if state.supplied:
            msg = "--input-json cannot be combined with body assignments"
            raise UsageError(msg, details=[("inputs", ", ".join(sorted(set(state.supplied))))])
        binding.body = validate_json_body(cap, input_json)
        binding.body_is_raw = True
        return
    if state.scalars or state.arrays:
        binding.body = dict(state.scalars)
        binding.body.update(state.arrays)


def _reject_duplicate(seen: set[tuple[str, str]], location: str, name: str, source: str) -> None:
    key = (location, name)
    if key in seen:
        msg = f"{name} was supplied more than once and is not an array input"
        raise UsageError(msg, details=[("input", name), ("source", source)])
    seen.add(key)


def _missing_body_inputs(
    cap: Capability,
    binding: Binding,
    supplied_body_names: Sequence[str],
) -> list[str]:
    declared = body_properties(cap)
    supplied = _supplied_body_names(binding, supplied_body_names)
    required_body = cap.body is not None and cap.body.required
    if not declared or not (supplied or required_body):
        return []
    return [
        f"body:{name}"
        for name in body_schema(cap).get("required") or []
        if name in declared and name not in supplied
    ]


def _supplied_body_names(binding: Binding, assigned: Sequence[str]) -> set[str]:
    """Which body properties the caller supplied, however they supplied them."""
    if binding.body_is_raw and isinstance(binding.body, dict):
        return set(binding.body)
    return set(assigned)


def _missing_params(cap: Capability, location: str, supplied: set[str]) -> list[str]:
    """Every required input in one location the caller did not supply."""
    label = QUALIFIERS_INVERSE[location]
    return [
        f"{label}:{param.name}"
        for param in cap.params_in(location)
        if param.required and param.name not in supplied
    ]


def _check_required(cap: Capability, binding: Binding, supplied_body_names: Sequence[str]) -> None:
    supplied_query = {name for name, _ in binding.query}
    supplied_form = {name for name, _ in binding.form} | {name for name, _ in binding.files}
    missing = _missing_params(cap, "query", supplied_query)
    missing += _missing_params(cap, "formData", supplied_form)
    missing += _missing_body_inputs(cap, binding, supplied_body_names)
    if missing:
        msg = "missing required input " + ", ".join(missing)
        raise UsageError(
            msg,
            details=[("capability", cap.key), ("missing", ", ".join(missing))],
            help_commands=build(capability(cap.key)),
        )


def _apply_pagination(cap: Capability, binding: Binding) -> None:
    names = {param.name for param in cap.params_in("query")}
    if not {"page", "limit"} <= names:
        return
    supplied = {name for name, _ in binding.query}
    for name, value in (("page", DEFAULT_PAGE), ("limit", DEFAULT_LIMIT)):
        if name not in supplied:
            binding.query.append((name, str(value)))
            binding.defaults.append((name, value))
