"""The capability model.

A capability is one advertised operation, normalized away from the dialect it
was described in. Nothing here knows about Swagger; the compiler in
`gaxi.swagger` produces these values and the rest of the bridge consumes them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaxi.jsonshape import JsonObject, JsonValue

LOCATION_NAMES = {"query": "query", "body": "body", "formData": "form"}
FIRST_SUCCESS = 200
FIRST_REDIRECT = 300
LAST_REDIRECT = 400


class UnsupportedError(Exception):
    """A construct v1 cannot compile; it disables one capability."""


@dataclass(kw_only=True)
class Param:
    """One declared capability input."""

    name: str
    location: str
    required: bool = False
    type: str | None = None
    enum: list[JsonValue] | None = None
    items_type: str | None = None
    items_enum: list[JsonValue] | None = None
    collection_format: str | None = None
    description: str = ""
    schema: JsonObject | None = None
    default: JsonValue = None

    @property
    def binding_location(self) -> str:
        """Where a binding places this input, in the bridge's vocabulary."""
        return LOCATION_NAMES.get(self.location, self.location)

    @property
    def is_array(self) -> bool:
        """Whether the input takes several values."""
        return self.type == "array"

    @property
    def is_file(self) -> bool:
        """Whether the input is an uploaded file."""
        return self.type == "file"


@dataclass(kw_only=True)
class ResponseSpec:
    """One advertised response for a capability."""

    status: int
    kind: str  # collection | object | text | file | empty | redirect | unknown
    schema: JsonObject | None = None
    entity_ref: str | None = None
    headers: JsonObject = field(default_factory=dict)
    description: str = ""


@dataclass(kw_only=True)
class Capability:
    """A normalized advertised operation."""

    method: str
    path: str
    operation_id: str = ""
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    params: list[Param] = field(default_factory=list)
    body: Param | None = None
    produces: list[str] = field(default_factory=list)
    consumes: list[str] = field(default_factory=list)
    responses: dict[int, ResponseSpec] = field(default_factory=dict)
    unsupported: str | None = None
    matcher: re.Pattern[str] = field(init=False, repr=False)
    specificity: tuple[int, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Derive the path matcher and the routing specificity."""
        self.matcher = _compile_matcher(self.path)
        self.specificity = _specificity(self.path)

    @property
    def key(self) -> str:
        """The `method:path` identity used to address this capability."""
        return f"{self.method}:{self.path}"

    @property
    def available(self) -> bool:
        """Whether the capability compiled without an unsupported construct."""
        return self.unsupported is None

    def params_in(self, location: str) -> list[Param]:
        """Every declared input in one Swagger location."""
        return [p for p in self.params if p.location == location]

    def success_response(self) -> ResponseSpec | None:
        """The lowest advertised 2xx/3xx response, or None."""
        for status in sorted(self.responses):
            if FIRST_SUCCESS <= status < FIRST_REDIRECT + 100:
                return self.responses[status]
        return None

    def declares(self, name: str) -> bool:
        """Whether an input of this name is declared."""
        return any(p.name == name for p in self.params)


def _piece_pattern(piece: str) -> str:
    """One literal or one `{name}` placeholder, as a regular expression."""
    if piece.startswith("{") and piece.endswith("}"):
        group = re.sub(r"[^0-9a-zA-Z_]", "_", piece[1:-1])
        return f"(?P<{group}>[^/]+?)"
    return re.escape(piece)


def _segment_pattern(segment: str) -> str:
    """One path segment, which may mix literals and placeholders."""
    return "".join(
        _piece_pattern(piece)
        for piece in re.split(r"(\{[^{}]+\})", segment)
        if piece
    )


def _compile_matcher(path: str) -> re.Pattern[str]:
    parts = [_segment_pattern(s) for s in path.strip("/").split("/") if s]
    return re.compile("^/" + "/".join(parts) + "$") if parts else re.compile("^/$")


def _specificity(path: str) -> tuple[int, int]:
    segments = [s for s in path.strip("/").split("/") if s]
    static = sum(1 for s in segments if "{" not in s)
    partial = sum(1 for s in segments if "{" in s and not _whole_parameter(s))
    return (static, partial)


def _whole_parameter(segment: str) -> bool:
    return (segment.startswith("{") and segment.endswith("}")
            and segment.count("{") == 1)
