"""Swagger 2.0 compiler.

The compiler normalizes an instance description into a capability catalog. It
never exposes Swagger objects to the rest of the bridge, and an unsupported
construct disables only the capability that contains it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from gaxi.capability import Capability, Param, ResponseSpec, UnsupportedError
from gaxi.http import FIRST_SUCCESS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaxi.jsonshape import JsonObject, JsonValue

SCALAR_TYPES = {"string", "integer", "number", "boolean"}
BINDABLE_LOCATIONS = {"query", "body", "formData"}
PARAMETER_LOCATIONS = ("path", "query", "header", "body", "formData")
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")
MAX_REFERENCE_DEPTH = 16
REDIRECT_STATUSES = range(300, 400)
EMPTY_STATUSES = (204, 304)


class Description:
    """A parsed instance description."""

    def __init__(self, raw: JsonObject) -> None:
        self.raw = raw
        self.base_path = raw.get("basePath") or "/"
        info = raw.get("info") or {}
        self.title = info.get("title") or ""
        self.version = info.get("version") or ""
        self.schemes = list(raw.get("schemes") or [])
        self.security_definitions = dict(raw.get("securityDefinitions") or {})

    def resolve(self, node: JsonValue) -> JsonValue:
        """Resolve internal `$ref` values one level at a time, with a cycle bound."""
        seen = 0
        while isinstance(node, dict) and "$ref" in node:
            ref = node["$ref"]
            seen += 1
            if seen > MAX_REFERENCE_DEPTH:
                msg = f"cyclic reference {ref}"
                raise UnsupportedError(msg)
            node = self._dereference(ref)
        return node

    def _dereference(self, ref: JsonValue) -> JsonValue:
        """Follow one internal JSON pointer."""
        if not isinstance(ref, str) or not ref.startswith("#/"):
            msg = f"external reference {ref}"
            raise UnsupportedError(msg)
        target: JsonValue = self.raw
        for raw_part in ref[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or part not in target:
                msg = f"unresolvable reference {ref}"
                raise UnsupportedError(msg)
            target = target[part]
        return target


def _ref_name(node: JsonValue) -> str | None:
    ref = node.get("$ref") if isinstance(node, dict) else None
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None


def _param(description: Description, raw: JsonValue) -> Param:
    raw = description.resolve(raw)
    location = raw.get("in")
    name = raw.get("name")
    if not location or not name:
        msg = "parameter without a name or location"
        raise UnsupportedError(msg)
    if location not in PARAMETER_LOCATIONS:
        msg = f"unsupported parameter location {location}"
        raise UnsupportedError(msg)
    if location == "body":
        schema = description.resolve(raw.get("schema") or {})
        return Param(
            name=name,
            location=location,
            required=bool(raw.get("required")),
            type="object",
            description=raw.get("description") or "",
            schema=schema,
        )
    type_, items = _param_type(raw, name)
    items_type = items.get("type") if type_ == "array" else None
    return Param(
        name=name,
        location=location,
        required=bool(raw.get("required")),
        type=type_,
        enum=raw.get("enum"),
        items_type=items_type,
        items_enum=items.get("enum"),
        description=raw.get("description") or "",
        default=raw.get("default"),
    )


def _param_type(raw: JsonValue, name: str) -> tuple[str, JsonObject]:
    """The declared parameter type and its item schema, both supported."""
    type_ = raw.get("type")
    if type_ not in SCALAR_TYPES | {"array", "file"}:
        msg = f"unsupported parameter type {type_!r} for {name}"
        raise UnsupportedError(msg)
    items: JsonObject = raw.get("items") or {}
    if type_ == "array" and items.get("type") not in SCALAR_TYPES:
        msg = f"unsupported array item type {items.get('type')!r} for {name}"
        raise UnsupportedError(msg)
    return str(type_), items


def _response(
    description: Description,
    status: int,
    raw: JsonValue,
    produces: Sequence[str],
) -> ResponseSpec:
    raw = description.resolve(raw)
    headers = dict(raw.get("headers") or {})
    schema_node = raw.get("schema")
    if schema_node is None:
        return ResponseSpec(
            status=status,
            kind=_bodiless_kind(status),
            headers=headers,
            description=raw.get("description") or "",
        )
    kind, schema, entity_ref = _shape(description, schema_node)
    if kind in {"object", "collection"} and _only_text(produces):
        kind = "text"
    return ResponseSpec(
        status=status,
        kind=kind,
        schema=schema,
        entity_ref=entity_ref,
        headers=headers,
        description=raw.get("description") or "",
    )


def _bodiless_kind(status: int) -> str:
    """What a response with no declared schema is."""
    if status in REDIRECT_STATUSES:
        return "redirect"
    if status in EMPTY_STATUSES or status < FIRST_SUCCESS:
        return "empty"
    return "unknown"


def _shape(description: Description, schema_node: JsonValue) -> tuple[str, JsonObject, str | None]:
    """The response kind, resolved schema, and referenced entity."""
    entity_ref = _ref_name(schema_node)
    schema = description.resolve(schema_node)
    schema_type = schema.get("type")
    if schema_type == "array":
        items = schema.get("items") or {}
        resolved = {"type": "array", "items": description.resolve(items)}
        return "collection", resolved, _ref_name(items) or entity_ref
    kinds = {"file": "file", "string": "text"}
    return kinds.get(schema_type, "object"), schema, entity_ref


def _only_text(produces: Sequence[str]) -> bool:
    return bool(produces) and all(
        media.startswith("text/") or media == "text/html" for media in produces
    )


def compile_description(raw: JsonObject) -> tuple[list[Capability], Description]:
    """Compile a Swagger 2.0 document into capabilities.

    Returns `(capabilities, description)`. Capabilities whose Swagger contains a
    construct v1 does not support are returned with an `unsupported` reason.
    """
    description = Description(raw)
    produces = list(raw.get("produces") or [])
    consumes = list(raw.get("consumes") or [])
    capabilities: list[Capability] = []
    for path, path_item in (raw.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        shared = path_item.get("parameters") or []
        capabilities.extend(
            _capability(
                description, method, path, operation, shared,
                produces=produces, consumes=consumes,
            )
            for method, operation in _operations(path_item)
        )
    capabilities.sort(key=lambda cap: cap.key)
    return capabilities, description


def _operations(path_item: JsonObject) -> list[tuple[str, JsonObject]]:
    """Every advertised operation on one path, keyed by lowercase method."""
    return [
        (method.lower(), operation)
        for method, operation in path_item.items()
        if method.lower() in HTTP_METHODS and isinstance(operation, dict)
    ]


def _capability(
    description: Description,
    method: str,
    path: str,
    operation: JsonObject,
    shared: Sequence[JsonValue],
    *,
    produces: Sequence[str],
    consumes: Sequence[str],
) -> Capability:
    operation_produces = list(operation.get("produces") or produces)
    base = _base_fields(method, path, operation, operation_produces, consumes)
    try:
        params = [
            _param(description, raw)
            for raw in [*shared, *(operation.get("parameters") or [])]
        ]
        responses = _responses(description, operation, operation_produces)
        _check_path_params(path, params)
    except UnsupportedError as exc:
        return Capability(unsupported=str(exc), **base)
    body = next((param for param in params if param.location == "body"), None)
    return Capability(params=params, body=body, responses=responses, **base)


def _base_fields(
    method: str,
    path: str,
    operation: JsonObject,
    produces: Sequence[str],
    consumes: Sequence[str],
) -> JsonObject:
    """The capability fields that never depend on an unsupported construct."""
    return {
        "method": method,
        "path": path,
        "operation_id": operation.get("operationId") or "",
        "summary": operation.get("summary") or "",
        "description": operation.get("description") or "",
        "tags": list(operation.get("tags") or []),
        "produces": list(produces),
        "consumes": list(operation.get("consumes") or consumes),
    }


def _responses(
    description: Description,
    operation: JsonObject,
    produces: Sequence[str],
) -> dict[int, ResponseSpec]:
    """Every advertised response whose status is an integer."""
    return {
        code: _response(description, code, raw, produces)
        for code, raw in (
            (_status_code(status), raw)
            for status, raw in (operation.get("responses") or {}).items()
        )
        if code is not None
    }


def _status_code(status: JsonValue) -> int | None:
    try:
        return int(status)
    except (TypeError, ValueError):
        return None


def _check_path_params(path: str, params: Sequence[Param]) -> None:
    declared = {p.name for p in params if p.location == "path"}
    required = set(re.findall(r"\{([^{}]+)\}", path))
    missing = required - declared
    if missing:
        msg = "undeclared path parameter " + ", ".join(sorted(missing))
        raise UnsupportedError(msg)
