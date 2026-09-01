"""Bounded capability discovery and capability detail."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi.document import Aggregate, Document, Lines, Mapping, Scalar, Table
from gaxi.naming import command
from gaxi.policy import schema_field_names
from gaxi.suggestions import build, capabilities, capability, collect, lines

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaxi.capability import Capability
    from gaxi.jsonshape import JsonObject, JsonValue
    from gaxi.policy import Properties
    from gaxi.session import Session

DEFAULT_LIMIT = 20
SUMMARY_LIMIT = 160
MAX_PROJECTION_HINT = 4
POLICY_PROPERTIES = ("effect", "confirmation", "retry", "response", "entity", "projection")


def run(session: Session, terms: Sequence[str]) -> Document:
    """List advertised capabilities, filtered by search terms."""
    catalog = session.catalog
    policy = session.policy
    matched = catalog.search(terms)
    limit = session.options.limit or DEFAULT_LIMIT
    page = session.options.page or 1
    start = (page - 1) * limit
    window = matched[start:start + limit]

    document = Document()
    document.add("count", Aggregate(len(window), len(matched)))
    document.add("catalog", Scalar(len(catalog.available())))
    document.add("page", Scalar(page))
    unavailable = catalog.unavailable()
    if unavailable:
        document.add("unavailable", Scalar(len(unavailable)))
    rows: list[list[JsonValue]] = [
        [cap.method.upper(), cap.path, _summary(cap), policy.resolve(cap).effect]
        for cap in window
    ]
    document.add("capabilities", Table(["method", "path", "summary", "effect"], rows))
    rendered = lines(*_list_help(window, matched, terms, page, limit))
    _attach_help(document, rendered)
    return document


def _summary(cap: Capability) -> str:
    text = cap.summary or cap.operation_id or ""
    return text if len(text) <= SUMMARY_LIMIT else text[: SUMMARY_LIMIT - 1] + "…"


def _list_help(
    window: Sequence[Capability],
    matched: Sequence[Capability],
    terms: Sequence[str],
    page: int,
    limit: int,
) -> list[str]:
    suggestions: list[str | None] = []
    if window:
        suggestions.append(capability(window[0].key))
    if page * limit < len(matched):
        suggestions.append(capabilities(*terms, page=page + 1))
    elif not terms:
        suggestions.append(capabilities("issue"))
    return build(*suggestions)


def detail(session: Session, selector: str) -> Document:
    """Inspect one capability without expanding referenced schema trees."""
    catalog = session.catalog
    cap = catalog.select(selector)
    props = session.policy.resolve(cap)

    document = Document()
    mapping = Mapping()
    mapping.add("key", Scalar(cap.key))
    if cap.operation_id:
        mapping.add("operation_id", Scalar(cap.operation_id))
    if cap.summary:
        mapping.add("summary", Scalar(cap.summary))
    if cap.tags:
        mapping.add("tags", Scalar(",".join(cap.tags)))
    if not cap.available:
        mapping.add("available", Scalar(value=False))
        mapping.add("reason", Scalar(cap.unsupported))
        document.add("capability", mapping)
        _attach_help(document, lines(capabilities()))
        return document
    mapping.add("effect", Scalar(props.effect))
    mapping.add("confirmation", Scalar(props.confirmation))
    mapping.add("retry", Scalar(props.retry))
    mapping.add("response", Scalar(props.response))
    mapping.add("entity", Scalar(props.entity))
    if props.projection:
        mapping.add("projection", Scalar(",".join(props.projection)))
    document.add("capability", mapping)

    document.add("inputs", Table(
        ["name", "location", "type", "required"], _input_rows(cap)))
    document.add("responses", Table(
        ["status", "shape", "entity"],
        [[status, spec.kind, spec.entity_ref or ""]
         for status, spec in sorted(cap.responses.items())],
    ))
    document.add("policy", Table(
        ["property", "value", "source"],
        [[name, _property_value(getattr(props, name)), props.sources.get(name, "fallback")]
         for name in POLICY_PROPERTIES
         if getattr(props, name) is not None],
    ))
    _attach_help(document, lines(*_capability_help(cap, props)))
    return document


def _attach_help(document: Document, rendered: Lines | None) -> None:
    if rendered is not None:
        document.add("help", rendered)


def _property_value(value: JsonValue) -> JsonValue:
    return ",".join(str(item) for item in value) if isinstance(value, list) else value


def _input_rows(cap: Capability) -> list[list[JsonValue]]:
    rows: list[list[JsonValue]] = [
        [param.name, param.binding_location, param.type or "string", bool(param.required)]
        for param in cap.params
        if param.location != "body"
    ]
    body_schema = cap.body.schema if cap.body and cap.body.schema else {}
    required_names = body_schema.get("required") or []
    rows += [
        [name, "body", (schema or {}).get("type", "string"), name in required_names]
        for name, schema in _body_properties(cap).items()
    ]
    return rows


def _body_properties(cap: Capability) -> JsonObject:
    if cap.body is None or not isinstance(cap.body.schema, dict):
        return {}
    properties: JsonObject = cap.body.schema.get("properties") or {}
    return properties


def _capability_help(cap: Capability, props: Properties) -> list[str]:
    example = cap.path
    for segment in cap.path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            example = example.replace(segment, f"<{segment[1:-1]}>")
    suggestions = [command(cap.method, example)]
    if props.confirmation == "required":
        suggestions[0] += " --yes"
    elif props.confirmation == "unknown":
        suggestions[0] += " --allow-unknown"
    fields = schema_field_names(cap.success_response())
    if fields:
        projection = ",".join(fields[:MAX_PROJECTION_HINT])
        suggestions.append(command(cap.method, example, options=[f"--fields {projection}"]))
    return collect(*suggestions)
