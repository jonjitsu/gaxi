"""Result shaping: what one classified response becomes.

The invoker decides whether a request may be sent; this module decides what the
response looks like once it has come back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi import projection, render
from gaxi.document import Document, Lines, Mapping, Scalar, Table
from gaxi.errors import EXIT_FAILURE, GaxiError
from gaxi.fields import MAX_DECLARED_FIELDS
from gaxi.fields import fields as resolve_fields
from gaxi.invocation import Outcome
from gaxi.naming import command
from gaxi.planner import FORBIDDEN
from gaxi.policy import fallback_projection, schema_field_names
from gaxi.suggestions import build, collect, prepend

if TYPE_CHECKING:

    from collections.abc import Iterable, Sequence

    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.classify import Classification
    from gaxi.invocation import Invocation
    from gaxi.jsonshape import JsonValue
    from gaxi.planner import Planner
    from gaxi.policy import Properties
    from gaxi.transport import Response


MAX_ERROR_ITEMS = 3


def render_classification(
    inv: Invocation,
    classification: Classification,
    *,
    response: Response,
) -> Outcome:
    """Shape one classified response into the result the caller receives."""
    request = inv.request
    if classification.kind == "error":
        details: list[tuple[str, JsonValue]] = []
        if classification.status == FORBIDDEN:
            credential = inv.session.credential
            if credential:
                details.append(("credential", credential.source))
        return Outcome(
            render.error(
                _error_message(classification),
                status=classification.status,
                request=inv.request_line,
                details=details,
                help_commands=inv.planner.for_error(classification.status),
            ),
            exit_code=EXIT_FAILURE,
        )
    if request.raw:
        return Outcome(raw=response.read_all())
    return Outcome(_document_for(inv, classification))


def render_batch_collection(inv: Invocation, classification: Classification) -> Outcome:
    """Shape a synthetic batch collection into the result the caller receives."""
    request = inv.request
    items = classification.payload or []
    fields = _resolve_batch_fields(inv.cap, inv.props, items, request.fields)
    if request.fields is None:
        fields = _batch_result_fields(fields, items)
    rows, truncations = projection.project_rows(items, fields, full=request.full)
    help_commands = inv.planner.for_collection(
        classification,
        fields,
        allow_policy_fallback=not request.fields,
    )
    if truncations:
        help_commands = build(
            *_batch_truncation_help(inv.planner, items, truncations),
            *help_commands,
        )
    document = render.collection(
        inv.props.entity or "results",
        fields,
        rows,
        len(items),
        total=classification.total,
        truncations=truncations,
        help_commands=help_commands,
    )
    return Outcome(document)


def _batch_truncation_help(
    planner: Planner,
    items: Sequence[JsonValue],
    truncations: Iterable[tuple[int, str, int]],
) -> list[str]:
    """Safe detail-retrieval suggestions for truncated batch result rows."""
    by_row = _truncated_fields_by_row(truncations)
    return collect(
        *(
            suggestion
            for row_index, fields in sorted(by_row.items())
            if (suggestion := _detail_fields_full_for_row(planner, items, row_index, fields))
            is not None
        ),
    )


def _truncated_fields_by_row(
    truncations: Iterable[tuple[int, str, int]],
) -> dict[int, list[str]]:
    by_row: dict[int, list[str]] = {}
    for row_index, field, _original in truncations:
        row_fields = by_row.setdefault(row_index, [])
        if field not in row_fields:
            row_fields.append(field)
    return by_row


def _detail_fields_full_for_row(
    planner: Planner,
    items: Sequence[JsonValue],
    row_index: int,
    fields: Sequence[str],
) -> str | None:
    item_index = row_index - 1
    if item_index < 0 or item_index >= len(items):
        return None
    item = items[item_index]
    if not isinstance(item, dict):
        return None
    return planner.detail_fields_full(item, fields)


def _resolve_batch_fields(
    cap: Capability,
    props: Properties,
    items: Sequence[JsonValue],
    selected: Sequence[str] | None,
) -> list[str]:
    """Choose batch row fields without applying collection-item schema to wrappers."""
    if selected:
        return resolve_fields(cap, props, items, selected)
    if _batch_items_use_declared_fields(items, schema_field_names(cap.success_response())):
        return resolve_fields(cap, props, items, None)
    observed = projection.observed_fields(items)
    if observed:
        chosen = fallback_projection(observed) or observed[:MAX_DECLARED_FIELDS]
        return list(chosen)
    return resolve_fields(cap, props, items, None)


def _batch_items_use_declared_fields(
    items: Sequence[JsonValue],
    declared: Sequence[str],
) -> bool:
    """Whether batch rows already expose the capability's declared response fields."""
    if not declared:
        return False
    names = set(declared)
    return any(
        isinstance(item, dict) and names & set(item)
        for item in items
    )


def _batch_result_fields(fields: list[str], items: Sequence[JsonValue]) -> list[str]:
    """Prefer error columns when a batch mixed successes and failures."""
    if not any(isinstance(item, dict) and "error" in item for item in items):
        return fields
    error_fields = ("error", "status")
    leading = [name for name in error_fields if name in fields]
    missing = [name for name in error_fields if name not in fields]
    remaining = MAX_DECLARED_FIELDS - len(leading) - len(missing)
    others = [name for name in fields if name not in error_fields][:remaining]
    return leading + missing + others


def _document_for(inv: Invocation, classification: Classification) -> Document:
    kind = classification.kind
    if kind == "redirect":
        return render.redirect(classification.status, classification.payload)
    if kind == "binary":
        msg = "the instance returned an undocumented binary response"
        raise GaxiError(
            msg,
            status=classification.status,
            request=inv.request_line,
            details=[("media_type", classification.media_type)],
            help_commands=build(inv.planner.retry(["--save ./download.bin"])),
        )
    if kind == "text":
        return _text_document(inv, classification)
    if kind == "status":
        return render.status_result(
            classification.status,
            help_commands=_status_help(inv.planner),
        )
    if kind == "collection":
        return _collection_document(inv, classification)
    return _detail_document(inv, classification)


def _status_help(planner: Planner) -> list[str]:
    return build(planner.parent_collection())


def _reported(value: JsonValue) -> str:
    """One reported failure value, flattened to a single line."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return "; ".join(str(item) for item in value[:MAX_ERROR_ITEMS])
    return ""


def _error_message(classification: Classification) -> str:
    payload = classification.payload
    if isinstance(payload, dict):
        for key in ("message", "error", "errors"):
            reported = _reported(payload.get(key))
            if reported:
                return reported
    return f"request failed with status {classification.status}"


def _collection_document(inv: Invocation, classification: Classification) -> Document:
    request = inv.request
    items = classification.payload or []
    fields = resolve_fields(inv.cap, inv.props, items, request.fields)
    rows, truncations = projection.project_rows(items, fields, full=request.full)
    if not items:
        return render.collection(
            inv.props.entity or "results",
            fields,
            [],
            0,
            total=classification.total,
            help_commands=inv.planner.for_empty_collection(),
        )
    help_commands = inv.planner.for_collection(
        classification,
        fields,
        allow_policy_fallback=not inv.request.fields,
    )
    if truncations:
        help_commands = prepend(inv.planner.fields_full(fields), *help_commands)
    return render.collection(
        inv.props.entity or "results",
        fields,
        rows,
        len(items),
        total=classification.total,
        page=classification.page,
        truncations=truncations,
        help_commands=help_commands,
    )


def _detail_document(inv: Invocation, classification: Classification) -> Document:
    request = inv.request
    value = classification.payload
    items = [value] if isinstance(value, dict) else []
    fields = resolve_fields(inv.cap, inv.props, items, request.fields)
    pairs, truncations = projection.project_object(value, fields, full=request.full)
    help_commands = inv.planner.for_detail(classification, effect=inv.props.effect)
    if truncations:
        help_commands = prepend(inv.planner.fields_full(fields), *help_commands)
    return render.detail(
        inv.props.entity_singular or inv.props.entity or "result",
        pairs,
        truncations=truncations,
        help_commands=help_commands,
    )


def _text_document(inv: Invocation, classification: Classification) -> Document:
    text = classification.payload or ""
    shortened, original = projection.truncate(text, full=inv.request.full)
    help_commands = build(
        inv.planner.retry(["--raw"]) if original is not None else None,
    )
    return render.content(
        classification.media_type,
        len(text.encode("utf-8")),
        shortened,
        truncated=original is not None,
        help_commands=help_commands,
    )


def dry_run_document(inv: Invocation) -> Document:
    """What would have been sent, and what policy says about it."""
    binding = inv.binding
    document = Document()
    document.add("dry_run", _dry_run_mapping(inv))

    defaults = {name for name, _ in binding.defaults}
    document.add(
        "inputs",
        Table(
            ["name", "location", "value", "source"],
            _input_rows(binding, defaults),
        ),
    )
    document.add(
        "help",
        Lines(
            [
                command(
                    inv.method,
                    inv.path,
                    [(name, value) for name, value in binding.query if name not in defaults],
                ),
            ]
        ),
    )
    return document


def _dry_run_mapping(inv: Invocation) -> Mapping:
    """What the request would address, and what policy says about it."""
    session = inv.session
    query = inv.binding.query_string()
    mapping = Mapping()
    request = f"{inv.method.upper()} {inv.path}" + (f"?{query}" if query else "")
    mapping.add("request", Scalar(request))
    mapping.add("url", Scalar(session.instance.url(inv.path, query)))
    mapping.add("capability", Scalar(inv.cap.key))
    if inv.cap.operation_id:
        mapping.add("operation_id", Scalar(inv.cap.operation_id))
    for name, value in inv.props.as_pairs():
        mapping.add(name, Scalar(value))
    mapping.add("server", Scalar(session.instance.origin))
    mapping.add("server_source", Scalar(session.instance.source))
    credential = session.credential
    mapping.add("credential", Scalar(credential.source if credential else "anonymous"))
    identity = _repository_identity(inv)
    if identity:
        mapping.add("repository", Scalar(identity))
    mapping.add("sent", Scalar(value=False))
    return mapping


def _repository_identity(inv: Invocation) -> str:
    """The ambient repository the request was made from, if there is one."""
    repository = inv.session.repository
    if not repository.in_repository:
        return ""
    remote = repository.origin_remote
    return remote.full_name if remote else ""


def _input_rows(binding: Binding, defaults: set[str]) -> list[list[JsonValue]]:
    rows: list[list[JsonValue]] = [
        [name, "query", value, "default" if name in defaults else "assignment"]
        for name, value in binding.query
    ]
    rows += [[name, "form", value, "assignment"] for name, value in binding.form]
    rows += [[name, "form", path, "file"] for name, path in binding.files]
    rows += _body_input_rows(binding)
    return rows


def _body_input_rows(binding: Binding) -> list[list[JsonValue]]:
    if binding.batch_bodies is not None:
        return _batch_body_rows(binding.batch_bodies)
    if isinstance(binding.body, dict):
        return [
            [name, "body", projection.cell_value(value), "assignment"]
            for name, value in binding.body.items()
        ]
    return []


def _batch_body_rows(bodies: list[JsonValue]) -> list[list[JsonValue]]:
    rows: list[list[JsonValue]] = []
    for index, body in enumerate(bodies):
        if isinstance(body, dict):
            rows += [
                [f"[{index}].{name}", "body", projection.cell_value(value), "input-json"]
                for name, value in body.items()
            ]
        else:
            rows.append([f"[{index}]", "body", projection.cell_value(body), "input-json"])
    return rows
