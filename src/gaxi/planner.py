"""The next-action planner.

Suggestions are executable command templates: they carry forward the fixed
context of the request and use `<name>` placeholders only for values the caller
still has to supply.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from gaxi.naming import command, executable
from gaxi.policy import IDENTIFIER_FIELDS

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.catalog import Catalog
    from gaxi.classify import Classification
    from gaxi.jsonshape import JsonValue
    from gaxi.session import Options

PAGINATION = ("page", "limit")
MIN_DETAIL_SEGMENTS = 2
UNAUTHORIZED = (401, 403)
NOT_FOUND = 404
UNPROCESSABLE = 422

PLACEHOLDER = re.compile(r"^\{([^{}]+)\}$")

# Path-parameter names and their payload synonyms, tried before the generic fallback.
_PARAM_SYNONYMS: dict[str, tuple[str, ...]] = {
    "index": ("index", "number"),
    "number": ("number", "index"),
}


class Planner:
    """Builds one to three concrete next actions for a result."""

    def __init__(
        self,
        catalog: Catalog,
        cap: Capability,
        path: str,
        binding: Binding,
        options: Options,
    ) -> None:
        self.catalog = catalog
        self.cap = cap
        self.path = path
        self.binding = binding
        self.options = options

    # command reconstruction ------------------------------------------------
    def _fixed_assignments(
        self,
        skip: Sequence[str] = PAGINATION,
    ) -> list[tuple[str, JsonValue]]:
        pairs: list[tuple[str, JsonValue]] = [
            (name, value) for name, value in self.binding.query if name not in skip
        ]
        if isinstance(self.binding.body, dict):
            pairs += [
                (f"body:{name}", value)
                for name, value in self.binding.body.items()
                if isinstance(value, str | int | float | bool)
            ]
        return pairs

    def retry(self, extra_options: Iterable[str] = ()) -> str:
        """The exact command that repeats this request with added options."""
        assignments = self._fixed_assignments(skip=())
        return command(self.cap.method, self.path, assignments, list(extra_options))

    # catalog-derived relationships ----------------------------------------
    def _child_of(
        self,
        template: str,
        extra_segments: int = 1,
    ) -> list[tuple[Capability, list[str]]]:
        prefix = template.rstrip("/") + "/"
        found: list[tuple[Capability, list[str]]] = []
        for cap in self.catalog.available():
            if cap.method != "get" or not cap.path.startswith(prefix):
                continue
            rest = [s for s in cap.path[len(prefix):].split("/") if s]
            if len(rest) == extra_segments:
                found.append((cap, rest))
        return found

    def detail_suggestion(self) -> str | None:
        """`get <path>/<identifier>` when the catalog advertises the detail route."""
        for _cap, rest in self._child_of(self.cap.path):
            match = PLACEHOLDER.match(rest[0])
            if match:
                return command("get", f"{self.path.rstrip('/')}/<{match.group(1)}>")
        return None

    def related_suggestions(self, limit: int = 2) -> list[str]:
        """Concrete sub-resources of a detail route, such as its comments."""
        return self._related_at(self.cap.path, self.path, limit)

    def _related_at(self, template: str, path: str, limit: int = 2) -> list[str]:
        found: list[str] = []
        for _cap, rest in self._child_of(template):
            if PLACEHOLDER.match(rest[0]):
                continue
            found.append(command("get", f"{path.rstrip('/')}/{rest[0]}"))
            if len(found) >= limit:
                break
        return found

    def _resolved_detail(self, payload: dict[str, JsonValue]) -> tuple[str, str] | None:
        """The concrete detail path and catalog template for a created entity."""
        for cap, rest in self._child_of(self.cap.path):
            match = PLACEHOLDER.match(rest[0])
            if not match:
                continue
            value = _identifier_from_payload(payload, match.group(1))
            if value is None:
                continue
            detail_path = f"{self.path.rstrip('/')}/{value}"
            return detail_path, cap.path
        return None

    def next_page(self, classification: Classification) -> str | None:
        """A next-page command when metadata proves or a full page makes it plausible."""
        page = _int(dict(self.binding.query).get("page"))
        limit = _int(dict(self.binding.query).get("limit"))
        if page is None or limit is None:
            return None
        returned = len(classification.payload or [])
        proven = classification.has_next or (
            isinstance(classification.total, int) and page * limit < classification.total
        )
        if not proven and returned < limit:
            return None
        assignments = [*self._fixed_assignments(), ("page", page + 1), ("limit", limit)]
        return command(self.cap.method, self.path, assignments)

    def alternative_filter(self) -> str | None:
        """Another value for a declared enum filter, such as `state`."""
        supplied = dict(self.binding.query)
        for param in self.cap.params_in("query"):
            if not param.enum or param.name in PAGINATION:
                continue
            for value in param.enum:
                if str(value) != supplied.get(param.name):
                    assignments = self._fixed_assignments(skip=(*PAGINATION, param.name))
                    assignments.append((param.name, value))
                    return command(self.cap.method, self.path, assignments)
        return None

    def parent_collection(self) -> str | None:
        """The list capability that contains a missing detail resource."""
        parts = [part for part in self.path.strip("/").split("/") if part]
        if len(parts) < MIN_DETAIL_SEGMENTS:
            return None
        parent = "/" + "/".join(parts[:-1])
        if self.catalog.match("get", parent):
            return command("get", parent)
        return None

    def fields_full(self, fields: Sequence[str]) -> str:
        """The same request with an explicit projection and truncation disabled."""
        options = [f"--fields {','.join(fields)}", "--full"] if fields else ["--full"]
        return command(self.cap.method, self.path, self._fixed_assignments(skip=()), options)

    # composition -----------------------------------------------------------
    def for_collection(self, classification: Classification) -> list[str]:
        """Next actions for a collection result."""
        suggestions = [self.detail_suggestion(), self.next_page(classification)]
        if not any(suggestions):
            suggestions.append(self.alternative_filter())
        return _first(suggestions, 2)

    def for_empty_collection(self) -> list[str]:
        """Next actions when a collection came back empty."""
        return _first([self.alternative_filter(), self.parent_collection()], 2)

    def for_detail(
        self,
        classification: Classification | None = None,
        *,
        effect: str | None = None,
    ) -> list[str]:
        """Next actions for a detail result."""
        payload = classification.payload if classification else None
        if effect == "mutate" and isinstance(payload, dict):
            resolved = self._resolved_detail(payload)
            if resolved is not None:
                detail_path, detail_template = resolved
                suggestions = [
                    command("get", detail_path),
                    *self._related_at(detail_template, detail_path),
                ]
                return _first(suggestions, 2)
        return _first(self.related_suggestions(), 2)

    def for_error(self, status: int) -> list[str]:
        """Next actions for a failed request, chosen by status."""
        if status in UNAUTHORIZED:
            return [f"{executable()} auth add {self.catalog.origin}".strip()]
        if status == NOT_FOUND:
            return _first([self.parent_collection()], 1)
        if status == UNPROCESSABLE:
            return [f"{executable()} capability {self.cap.key}"]
        return []


def _first(candidates: Iterable[str | None], limit: int) -> list[str]:
    found: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in found:
            found.append(candidate)
        if len(found) >= limit:
            break
    return found


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _identifier_from_payload(payload: dict[str, JsonValue], param: str) -> JsonValue | None:
    """One externally usable identifier from a mutation response payload."""
    synonyms = _PARAM_SYNONYMS.get(param, (param,))
    candidates = (*synonyms, *IDENTIFIER_FIELDS)
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        value = payload.get(name)
        if _is_usable_identifier(value):
            return value
    return None


def _is_usable_identifier(value: JsonValue) -> bool:
    if isinstance(value, str):
        return bool(value)
    return isinstance(value, int) and not isinstance(value, bool)
