"""The next-action planner.

Suggestions are executable command templates: they carry forward the fixed
context of the request and use `<name>` placeholders only for values the caller
still has to supply.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from gaxi.http import parse_int
from gaxi.jsonbody import body_properties
from gaxi.naming import command, shell_quote
from gaxi.policy import FIELD_SYNONYMS, IDENTIFIER_FIELDS
from gaxi.suggestions import auth_add, batch_bodies, capability, collect

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.catalog import Catalog
    from gaxi.classify import Classification
    from gaxi.credentials import Credential
    from gaxi.jsonshape import JsonValue
    from gaxi.session import Session

PAGINATION = ("page", "limit")
MAX_BATCH_TEMPLATE_FIELDS = 3
MIN_DETAIL_SEGMENTS = 2
UNAUTHORIZED = 401
FORBIDDEN = 403
NOT_FOUND = 404
UNPROCESSABLE = 422

PLACEHOLDER = re.compile(r"^\{([^{}]+)\}$")

class Planner:
    """Builds one to three concrete next actions for a result."""

    def __init__(
        self,
        catalog: Catalog,
        cap: Capability,
        path: str,
        binding: Binding,
        session: Session | None = None,
    ) -> None:
        self.catalog = catalog
        self.cap = cap
        self.path = path
        self.binding = binding
        self.session = session

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

    def _placeholder_assignments(self) -> list[tuple[str, JsonValue]]:
        """Runnable placeholders for body properties the caller has not bound yet."""
        if self.binding.is_batch() or self.binding.body_is_raw:
            return []
        declared = body_properties(self.cap)
        if not declared:
            return []
        supplied = (
            set(self.binding.body)
            if isinstance(self.binding.body, dict)
            else set()
        )
        return [
            (f"body:{name}", f"<{name}>")
            for name in sorted(declared)
            if name not in supplied
        ]

    def retry(self, extra_options: Iterable[str] = ()) -> str:
        """The exact command that repeats this request with added options."""
        assignments = self._fixed_assignments(skip=()) + self._placeholder_assignments()
        options = list(extra_options)
        if (input_json := self._input_json_option()) is not None:
            options.insert(0, input_json)
        return command(self.cap.method, self.path, assignments, options)

    def _input_json_option(self) -> str | None:
        """The ``--input-json`` flag when the batch payload is not in ``binding.body``."""
        if not self.binding.is_batch():
            return None
        return f"--input-json {shell_quote(self._batch_input_json())}"

    def _batch_input_json(self) -> str:
        """The original batch payload reference, or a canonical JSON re-serialisation."""
        if self.session is not None:
            request = self.session.options.request
            if (source := request.input_json_source) is not None:
                if source.startswith("@") or source == "-":
                    return source
                return source
            if request.input_json is not None:
                return request.input_json
        return json.dumps(self.binding.batch_bodies, separators=(",", ":"))

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

    def detail_suggestion(
        self,
        fields: Sequence[str] | None = None,
        *,
        allow_policy_fallback: bool = True,
    ) -> str | None:
        """`get <path>/<identifier>` when the catalog advertises the detail route."""
        for _cap, rest in self._child_of(self.cap.path):
            match = PLACEHOLDER.match(rest[0])
            if match:
                placeholder = _detail_placeholder(
                    self.cap,
                    match.group(1),
                    fields,
                    self.session,
                    allow_policy_fallback=allow_policy_fallback,
                )
                return command("get", f"{self.path.rstrip('/')}/<{placeholder}>")
        return None

    def related_suggestions(self) -> list[str]:
        """Concrete sub-resources of a detail route, such as its comments."""
        return self._related_at(self.cap.path, self.path)

    def _related_at(self, template: str, path: str) -> list[str]:
        found: list[str] = []
        for _cap, rest in self._child_of(template):
            if PLACEHOLDER.match(rest[0]):
                continue
            found.append(command("get", f"{path.rstrip('/')}/{rest[0]}"))
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
        page = parse_int(dict(self.binding.query).get("page"))
        limit = parse_int(dict(self.binding.query).get("limit"))
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

    def batch_suggestion(self) -> str | None:
        """The same mutation carrying several bodies, when it could have been batched.

        The template repeats the body this request already sent, so it is offered
        only for a small, wholly scalar body: truncating a longer one would hand
        the caller a command that silently drops fields, and spelling it out in
        full would cost more tokens than the suggestion is worth.
        """
        body = self.binding.body
        if self.binding.is_batch() or self.binding.body_is_raw:
            return None
        if not isinstance(body, dict) or not body:
            return None
        names = [
            name
            for name, value in body.items()
            if isinstance(value, str | int | float | bool)
        ]
        if len(names) != len(body) or len(names) > MAX_BATCH_TEMPLATE_FIELDS:
            return None
        return batch_bodies(self.cap.method, self.path, names)

    def detail_fields_full(
        self,
        payload: dict[str, JsonValue],
        fields: Sequence[str],
    ) -> str | None:
        """A read-only detail fetch for truncated fields in one created entity."""
        resolved = self._resolved_detail(payload)
        if resolved is None:
            return None
        detail_path, _ = resolved
        options = [f"--fields {','.join(fields)}", "--full"] if fields else ["--full"]
        return command("get", detail_path, [], options)

    # composition -----------------------------------------------------------
    def for_collection(
        self,
        classification: Classification,
        fields: Sequence[str] | None = None,
        *,
        allow_policy_fallback: bool = True,
    ) -> list[str]:
        """Next actions for a collection result."""
        return collect(
            self.detail_suggestion(fields, allow_policy_fallback=allow_policy_fallback),
            self.next_page(classification),
            self.alternative_filter(),
        )

    def for_empty_collection(self) -> list[str]:
        """Next actions when a collection came back empty."""
        return collect(self.alternative_filter(), self.parent_collection())

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
                return collect(
                    command("get", detail_path),
                    self.batch_suggestion(),
                    *self._related_at(detail_template, detail_path),
                )
        return collect(*self.related_suggestions())

    def for_error(self, status: int) -> list[str]:
        """Next actions for a failed request, chosen by status."""
        if status == UNAUTHORIZED or (status == FORBIDDEN and self._credential() is None):
            return collect(auth_add(self.catalog.origin))
        if status == FORBIDDEN:
            return collect(command("get", "/user", [], ["--fields login"]))
        if status == NOT_FOUND:
            return collect(self.parent_collection())
        if status == UNPROCESSABLE:
            return collect(capability(self.cap.key))
        return []

    def _credential(self) -> Credential | None:
        """The credential attached to this request, if any."""
        if self.session is None:
            return None
        return self.session.credential


def _first_identifier_field(fields: Sequence[str]) -> str | None:
    for field in fields:
        root = field.split(".")[0]
        if root in IDENTIFIER_FIELDS:
            return root
    return None


def _placeholder_compatible(path_param: str, field_name: str) -> bool:
    if field_name == path_param:
        return True
    return field_name in FIELD_SYNONYMS.get(path_param, ())


def _compatible_identifier(fields: Sequence[str], path_param: str) -> str | None:
    if (
        (name := _first_identifier_field(fields))
        and _placeholder_compatible(path_param, name)
    ):
        return name
    return None


def _detail_placeholder(
    cap: Capability,
    path_param: str,
    fields: Sequence[str] | None,
    session: Session | None,
    *,
    allow_policy_fallback: bool = True,
) -> str:
    """The placeholder name that matches the projected identifier when declared."""
    if fields is not None and (name := _compatible_identifier(fields, path_param)):
        return name
    if fields is not None and not allow_policy_fallback:
        return path_param
    if allow_policy_fallback and session is not None:
        projection = session.policy.resolve(cap).projection
        if projection and (name := _compatible_identifier(projection, path_param)):
            return name
    return path_param


def _identifier_from_payload(payload: dict[str, JsonValue], param: str) -> JsonValue | None:
    """One externally usable identifier from a mutation response payload."""
    synonyms = FIELD_SYNONYMS.get(param, (param,))
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
