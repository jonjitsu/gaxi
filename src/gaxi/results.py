"""Result shaping: what one classified response becomes.

The invoker decides whether a request may be sent; this module decides what the
response looks like once it has come back.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from gaxi import projection, render
from gaxi.document import Document, Lines, Mapping, Scalar, Table
from gaxi.errors import EXIT_FAILURE, GaxiError
from gaxi.invocation import Outcome
from gaxi.naming import command
from gaxi.planner import FORBIDDEN
from gaxi.policy import fallback_projection, schema_field_names
from gaxi.transport import CHUNK

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.classify import Classification
    from gaxi.invocation import Invocation
    from gaxi.jsonshape import JsonValue
    from gaxi.planner import Planner
    from gaxi.policy import Properties
    from gaxi.session import Options
    from gaxi.transport import Response


@runtime_checkable
class Digest(Protocol):
    """The part of a hash object this module relies on."""

    def update(self, data: bytes, /) -> None:
        """Add more bytes to the running digest."""
        ...

    def hexdigest(self) -> str:
        """The digest so far, as hexadecimal."""
        ...


FIRST_SUCCESS = 200
FIRST_REDIRECT = 300
MAX_HELP_COMMANDS = 3
MAX_ERROR_ITEMS = 3
MAX_DECLARED_FIELDS = 4


def render_classification(
    inv: Invocation,
    classification: Classification,
    *,
    response: Response,
) -> Outcome:
    """Shape one classified response into the result the caller receives."""
    options = inv.options
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
    if options.raw:
        return Outcome(raw=response.read_all())
    return Outcome(_document_for(inv, classification))


def render_save(inv: Invocation, response: Response) -> Document:
    """Save a successful response body to disk and return the receipt."""
    return _save(inv, response)


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
            help_commands=[inv.planner.retry(["--save ./download.bin"])],
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
    parent = planner.parent_collection()
    return [parent] if parent else []


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


def _declared_names(cap: Capability) -> list[str]:
    return schema_field_names(cap.success_response())


def _fields_for(
    cap: Capability,
    props: Properties,
    items: Sequence[JsonValue],
    options: Options,
) -> list[str]:
    if options.fields:
        projection.validate_fields(options.fields, items, _declared_names(cap))
        return list(options.fields)
    chosen = _policy_fields(cap, props, items)
    if chosen:
        return chosen
    observed = projection.observed_fields(items)
    if observed:
        return fallback_projection(observed)
    return _declared_names(cap)[:MAX_DECLARED_FIELDS]


def _policy_fields(
    cap: Capability,
    props: Properties,
    items: Sequence[JsonValue],
) -> list[str]:
    if not props.projection:
        return []
    available = set(projection.observed_fields(items)) | set(_declared_names(cap))
    if not available:
        return list(props.projection)
    return [field for field in props.projection if field.split(".")[0] in available]


def _capped(help_commands: Sequence[str], first: str) -> list[str]:
    return [first, *help_commands][:MAX_HELP_COMMANDS]


def _collection_document(inv: Invocation, classification: Classification) -> Document:
    options = inv.options
    items = classification.payload or []
    fields = _fields_for(inv.cap, inv.props, items, options)
    rows, truncations = projection.project_rows(items, fields, full=options.full)
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
        allow_policy_fallback=not inv.options.fields,
    )
    if truncations:
        help_commands = _capped(help_commands, inv.planner.fields_full(fields))
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
    options = inv.options
    value = classification.payload
    items = [value] if isinstance(value, dict) else []
    fields = _fields_for(inv.cap, inv.props, items, options)
    pairs, truncations = projection.project_object(value, fields, full=options.full)
    help_commands = inv.planner.for_detail(classification, effect=inv.props.effect)
    if truncations:
        help_commands = _capped(help_commands, inv.planner.fields_full(fields))
    return render.detail(
        inv.props.entity_singular or inv.props.entity or "result",
        pairs,
        truncations=truncations,
        help_commands=help_commands,
    )


def _text_document(inv: Invocation, classification: Classification) -> Document:
    text = classification.payload or ""
    shortened, original = projection.truncate(text, full=inv.options.full)
    help_commands = [inv.planner.retry(["--raw"])] if original is not None else []
    return render.content(
        classification.media_type,
        len(text.encode("utf-8")),
        shortened,
        truncated=original is not None,
        help_commands=help_commands,
    )


def _drain(response: Response, destination: Path, digest: Digest) -> int:
    """Write the whole response body to a file, hashing it on the way through."""
    size = 0
    with destination.open("wb") as handle:
        if response.stream is None:
            body = response.read_all()
            digest.update(body)
            handle.write(body)
            return len(body)
        while chunk := response.stream.read(CHUNK):
            digest.update(chunk)
            size += len(chunk)
            handle.write(chunk)
    return size


def _save(inv: Invocation, response: Response) -> Document:
    options = inv.options
    requested = options.save or ""
    destination = Path(requested).absolute()
    if destination.exists() and not options.overwrite:
        msg = f"{requested} already exists"
        raise GaxiError(
            msg,
            details=[("path", requested)],
            help_commands=[inv.planner.retry([f"--save {requested}", "--overwrite"])],
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".gaxi-{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    try:
        size = _drain(response, temporary, digest)
        temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        msg = f"cannot save response: {exc}"
        raise GaxiError(msg, details=[("path", requested)]) from exc
    return render.file_receipt(
        requested,
        size,
        response.media_type or "application/octet-stream",
        digest.hexdigest(),
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
    if isinstance(binding.body, dict):
        rows += [
            [name, "body", projection.cell_value(value), "assignment"]
            for name, value in binding.body.items()
        ]
    return rows
