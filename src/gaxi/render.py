"""Result shapes.

The renderer selects the smallest result shape that fully describes an outcome.
Successful responses never receive a universal HTTP envelope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi.document import Aggregate, Document, Mapping, Scalar, Table
from gaxi.suggestions import lines as suggestion_lines
from gaxi.suggestions import suppressed

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from gaxi.jsonshape import JsonValue


def _cell(value: JsonValue, *, truncated: bool) -> Scalar:
    return Scalar(value, quoted=truncated) if truncated else Scalar(value)


def collection(
    entity: str,
    fields: Sequence[str],
    rows: Iterable[Iterable[tuple[JsonValue, bool]]],
    returned: int,
    *,
    total: int | str | None = None,
    page: int | None = None,
    truncations: Iterable[tuple[int, str, int]] = (),
    help_commands: Iterable[str] = (),
) -> Document:
    """`count:` aggregate, then a named typed table."""
    document = Document()
    document.add("count", Aggregate(returned, total))
    if page is not None:
        document.add("page", Scalar(page))
    document.add(entity, Table(
        fields,
        [[_cell(value, truncated=flag) for value, flag in row] for row in rows],
    ))
    if truncations:
        document.add("truncated", Table(
            ["row", "field", "characters"],
            [list(entry) for entry in truncations],
        ))
    _add_help(document, help_commands)
    return document


def detail(
    entity: str,
    pairs: Iterable[tuple[str, JsonValue, bool]],
    truncations: Iterable[tuple[str, int]] = (),
    help_commands: Iterable[str] = (),
) -> Document:
    """A named detail object without the meaningless `count: 1` aggregate."""
    document = Document()
    mapping = Mapping()
    for field, value, truncated in pairs:
        mapping.add(field, _cell(value, truncated=truncated))
    document.add(entity, mapping)
    if truncations:
        document.add("truncated", Table(
            ["field", "characters"],
            [list(entry) for entry in truncations],
        ))
    _add_help(document, help_commands)
    return document


def status_result(
    status: int,
    outcome: str = "completed",
    extra: Iterable[tuple[str, JsonValue]] = (),
    help_commands: Iterable[str] = (),
) -> Document:
    """A successful response that carries no entity is never silent."""
    document = Document()
    mapping = Mapping().add("status", Scalar(status)).add("outcome", Scalar(outcome))
    for key, value in extra:
        mapping.add(key, Scalar(value))
    document.add("result", mapping)
    _add_help(document, help_commands)
    return document


def content(
    media_type: str,
    size: int,
    text: str,
    *,
    truncated: bool,
    help_commands: Iterable[str] = (),
) -> Document:
    """Structured, truncated non-JSON text."""
    document = Document()
    mapping = Mapping()
    mapping.add("media_type", Scalar(media_type))
    mapping.add("size", Scalar(size))
    mapping.add("truncated", Scalar(truncated))
    mapping.add("text", Scalar(text, quoted=True))
    document.add("content", mapping)
    _add_help(document, help_commands)
    return document


def file_receipt(
    path: str,
    size: int,
    media_type: str,
    digest: str,
    help_commands: Iterable[str] = (),
) -> Document:
    """A receipt for a response body streamed to a file."""
    document = Document()
    mapping = Mapping()
    mapping.add("path", Scalar(path))
    mapping.add("size", Scalar(size))
    mapping.add("media_type", Scalar(media_type))
    mapping.add("sha256", Scalar(digest))
    document.add("file", mapping)
    _add_help(document, help_commands)
    return document


def redirect(status: int, location: str, help_commands: Iterable[str] = ()) -> Document:
    """A redirect the invoker chose not to follow."""
    document = Document()
    mapping = Mapping().add("status", Scalar(status)).add("location", Scalar(location))
    document.add("redirect", mapping)
    _add_help(document, help_commands)
    return document


def error(
    message: str,
    status: int | None = None,
    request: str | None = None,
    details: Iterable[tuple[str, JsonValue]] = (),
    help_commands: Iterable[str] = (),
) -> Document:
    """Structured failures always leave on stdout."""
    document = Document()
    mapping = Mapping().add("message", Scalar(message))
    if status is not None:
        mapping.add("status", Scalar(status))
    if request:
        mapping.add("request", Scalar(request))
    for key, value in details:
        mapping.add(key, Scalar(value))
    document.add("error", mapping)
    _add_help(document, help_commands)
    return document


def _add_help(document: Document, help_commands: Iterable[str]) -> Document:
    if suppressed():
        return document
    rendered = suggestion_lines(*help_commands)
    if rendered is not None:
        document.add("help", rendered)
    return document
