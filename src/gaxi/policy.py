"""Capability-matched semantic policy.

Every semantic property is resolved layer by layer and keeps the name of the
layer that supplied it, so `gaxi capability` can report provenance:

1. non-overridable bridge invariants;
2. built-in capability-matched semantic policy;
3. user overlays bound to one exact instance origin;
4. repository-local presentation overlays;
5. conservative schema and runtime fallback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from gaxi import policy_data

if TYPE_CHECKING:
    from collections.abc import Container, Iterable, Sequence

    from gaxi.capability import Capability, ResponseSpec
    from gaxi.jsonshape import JsonObject, JsonValue
    from gaxi.swagger import Description

PRESENTATION_KEYS = ("entity", "entity_singular", "projection")
OVERLAY_KEYS = (*PRESENTATION_KEYS, "confirmation", "retry", "response")

IDENTIFIER_FIELDS = ("index", "id", "number", "sha", "login", "username", "uuid", "key")
SCALAR_TYPES = frozenset({"string", "integer", "number", "boolean"})
_LOGIN_SYNONYMS = ("login", "username", "org", "assignee", "collaborator", "user")
FIELD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "index": ("index", "number"),
    "number": ("number", "index"),
    **dict.fromkeys(_LOGIN_SYNONYMS, _LOGIN_SYNONYMS),
}
NAME_FIELDS = ("name", "title", "full_name", "tag_name", "path", "ref")
STATE_FIELDS = ("state", "status", "active", "unread")
VERBOSE_FIELDS = ("body", "description", "content", "message", "diff", "patch", "readme")
MAX_PROJECTION = 4
MIN_PLURAL = 3


class Properties:
    """The resolved semantic properties of one capability."""

    def __init__(self) -> None:
        self.effect: str | None = None
        self.confirmation: str | None = None
        self.retry: str | None = None
        self.entity: str | None = None
        self.entity_singular: str | None = None
        self.projection: list[str] | None = None
        self.response: str | None = None
        self.sources: dict[str, str] = {}

    def set_once(self, name: str, value: object, source: str) -> None:
        """Record a property and its layer, unless an earlier layer supplied it."""
        if value is None or getattr(self, name) is not None:
            return
        setattr(self, name, value)
        self.sources[name] = source

    def as_pairs(self) -> list[tuple[str, str | None]]:
        """The properties every result reports, in their reporting order."""
        return [
            ("effect", self.effect),
            ("confirmation", self.confirmation),
            ("retry", self.retry),
        ]


class Policy:
    """The layered semantic policy for one instance."""

    def __init__(
        self,
        user_overlay: JsonObject | None = None,
        repo_overlay: JsonObject | None = None,
    ) -> None:
        self.user_overlay: JsonObject = user_overlay or {}
        self.repo_overlay: JsonObject = repo_overlay or {}
        self.version = policy_data.BUNDLE_VERSION

    def resolve(self, cap: Capability) -> Properties:
        """Resolve every semantic property of one capability, layer by layer."""
        props = Properties()
        self._invariants(cap, props)
        self._builtin(cap, props)
        self._overlay(cap, props, self.user_overlay, "user-overlay", OVERLAY_KEYS)
        self._overlay(cap, props, self.repo_overlay, "repository-overlay", PRESENTATION_KEYS)
        self._fallback(cap, props)
        return props

    # layer 1
    def _invariants(self, cap: Capability, props: Properties) -> None:
        effect = "read" if cap.method in {"get", "head"} else "mutate"
        props.set_once("effect", effect, "invariant")
        if cap.method == "delete":
            props.set_once("confirmation", "required", "invariant")
            props.set_once("retry", "unsafe", "invariant")
        if cap.method == "get":
            props.set_once("confirmation", "none", "invariant")
            props.set_once("retry", "safe", "invariant")
        if cap.method == "post":
            props.set_once("retry", "unsafe", "invariant")

    # layer 2
    def _builtin(self, cap: Capability, props: Properties) -> None:
        rule = policy_data.MUTATIONS.get(cap.key)
        if rule:
            confirmation, retry = rule
            props.set_once("confirmation", confirmation, "builtin")
            props.set_once("retry", retry, "builtin")
        response = policy_data.RESPONSES.get(cap.key)
        props.set_once("response", response, "builtin")
        spec = cap.success_response()
        ref = spec.entity_ref if spec else None
        entity = policy_data.ENTITIES.get(ref) if ref else None
        if entity:
            collection, singular, projection = entity
            props.set_once("entity", collection, "builtin")
            props.set_once("entity_singular", singular, "builtin")
            props.set_once("projection", list(projection), "builtin")

    # layers 3 and 4
    def _overlay(
        self,
        cap: Capability,
        props: Properties,
        overlay: JsonObject,
        source: str,
        allowed: Sequence[str],
    ) -> None:
        entity_rule = self._entity_rule(cap, overlay)
        for key, value in entity_rule.items():
            if key in allowed and key in PRESENTATION_KEYS:
                props.set_once(key, value, source)
        rule = (overlay.get("capabilities") or {}).get(cap.key) or {}
        for key, value in rule.items():
            if key in allowed:
                props.set_once(key, value, source)

    @staticmethod
    def _entity_rule(cap: Capability, overlay: JsonObject) -> JsonObject:
        """The overlay rule bound to the capability's advertised entity."""
        spec = cap.success_response()
        if spec is None or not spec.entity_ref:
            return {}
        rule: JsonObject = (overlay.get("entities") or {}).get(spec.entity_ref) or {}
        return rule

    # layer 5
    def _fallback(self, cap: Capability, props: Properties) -> None:
        spec = cap.success_response()
        kind = spec.kind if spec else "unknown"
        props.set_once("response", kind, "schema")
        props.set_once("confirmation", "unknown", "fallback")
        props.set_once("retry", "unknown", "fallback")
        names = schema_field_names(spec)
        if props.entity is None:
            entity, singular = _fallback_entity(cap, props.response)
            props.set_once("entity", entity, "fallback")
            props.set_once("entity_singular", singular, "fallback")
        if props.projection is None and names:
            props.set_once("projection", fallback_projection(names), "fallback")


def _response_properties(spec: ResponseSpec | None) -> dict[str, Any]:
    if spec is None or not spec.schema:
        return {}
    schema = spec.schema
    if schema.get("type") == "array":
        schema = schema.get("items") or {}
    return schema.get("properties") or {}


def schema_field_names(spec: ResponseSpec | None) -> list[str]:
    """The scalar property names the advertised success response declares."""
    return [
        name for name, value in _response_properties(spec).items()
        if isinstance(value, dict)
        and value.get("type") in {"string", "integer", "number", "boolean"}
    ]


def schema_property_names(spec: ResponseSpec | None) -> list[str]:
    """Every property name the advertised success response declares."""
    return list(_response_properties(spec))


def entity_field_rows(
    description: Description,
    spec: ResponseSpec | None,
    projection: Sequence[str] | None,
) -> list[list[JsonValue]]:
    """Every scalar or array field on the success entity, with projection flags."""
    schema = _entity_schema(description, spec)
    if schema is None:
        return []
    projected = set(projection or [])
    seen: set[str] = set()
    if spec is not None and spec.entity_ref:
        seen.add(spec.entity_ref)
    return [
        [name, type_, name in projected]
        for name, type_ in _entity_field_paths(description, schema, seen=seen)
    ]


def _entity_schema(
    description: Description,
    spec: ResponseSpec | None,
) -> JsonObject | None:
    if spec is None:
        return None
    if spec.entity_ref:
        return _resolved_schema(description, {"$ref": f"#/definitions/{spec.entity_ref}"})
    return _inline_entity_schema(description, spec.schema)


def _resolved_schema(description: Description, node: JsonValue) -> JsonObject | None:
    resolved = description.resolve(node)
    return resolved if isinstance(resolved, dict) else None


def _inline_entity_schema(
    description: Description,
    schema: JsonValue,
) -> JsonObject | None:
    if not isinstance(schema, dict):
        return None
    schema_type = schema.get("type")
    if schema_type == "object":
        return schema
    if schema_type == "array":
        return _resolved_schema(description, schema.get("items") or {})
    return None


def _schema_ref_name(node: JsonValue) -> str | None:
    if isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        return ref.rsplit("/", 1)[-1] if isinstance(ref, str) else None
    return None


def _cyclic_object_field(prefix: str) -> list[tuple[str, str]]:
    return [(prefix, "object")] if prefix else []


def _entity_field_paths(
    description: Description,
    schema: JsonValue,
    *,
    prefix: str = "",
    seen: set[str],
) -> list[tuple[str, str]]:
    schema = description.resolve(schema)
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties") or {}
    rows: list[tuple[str, str]] = []
    for name, raw_prop in properties.items():
        path = f"{prefix}.{name}" if prefix else name
        rows.extend(_expand_entity_field(description, raw_prop, path, seen))
    return rows


def _expand_resolved_entity_field(
    description: Description,
    prop: JsonObject,
    raw_prop: JsonValue,
    path: str,
    seen: set[str],
) -> list[tuple[str, str]]:
    type_ = prop.get("type")
    if type_ in SCALAR_TYPES:
        return [(path, str(type_))]
    if type_ == "array":
        return [(path, "array")]
    if not _expandable_object(prop, raw_prop):
        return [(path, str(type_) if type_ else "unknown")]
    nested = _entity_field_paths(description, prop, prefix=path, seen=seen)
    return nested or _cyclic_object_field(path)


def _expand_entity_field(
    description: Description,
    raw_prop: JsonValue,
    path: str,
    seen: set[str],
) -> list[tuple[str, str]]:
    ref_name = _schema_ref_name(raw_prop)
    if ref_name is not None:
        if ref_name in seen:
            return _cyclic_object_field(path)
        child_seen = seen | {ref_name}
        nested = _entity_field_paths(description, raw_prop, prefix=path, seen=child_seen)
        return nested or _cyclic_object_field(path)
    prop = description.resolve(raw_prop)
    if not isinstance(prop, dict):
        return [(path, "unknown")]
    return _expand_resolved_entity_field(description, prop, raw_prop, path, seen)


def _expandable_object(prop: JsonObject, raw_prop: JsonValue) -> bool:
    return (
        prop.get("type") == "object"
        or _schema_ref_name(raw_prop) is not None
        or bool(prop.get("properties"))
    )


def _fallback_entity(cap: Capability, response_kind: str | None) -> tuple[str, str]:
    segments = [s for s in cap.path.strip("/").split("/") if s and "{" not in s]
    base = segments[-1] if segments else "result"
    base = base.replace("-", "_").replace(".", "_")
    singular = base[:-1] if base.endswith("s") and len(base) > MIN_PLURAL else base
    plural = base if base.endswith("s") else base + "s"
    if response_kind == "collection":
        return plural, singular
    return singular, singular


def _preferred(names: Container[str], group: Sequence[str], *, first_only: bool) -> list[str]:
    """The members of one preference group that the entity actually has."""
    found = [candidate for candidate in group if candidate in names]
    return found[:1] if first_only else found


def fallback_projection(names: Iterable[str]) -> list[str]:
    """A deterministic projection for an entity with no policy rule.

    Prefer an externally usable identifier, then a name or title, then a state,
    then the remaining short scalar properties in lexical order.
    """
    available = set(names)
    ordered = [
        *_preferred(available, IDENTIFIER_FIELDS, first_only=True),
        *_preferred(available, NAME_FIELDS, first_only=False),
        *_preferred(available, STATE_FIELDS, first_only=False),
        *sorted(name for name in available if not _is_verbose(name)),
    ]
    return list(dict.fromkeys(ordered))[:MAX_PROJECTION]


def _is_verbose(name: str) -> bool:
    lowered = name.lower()
    if lowered.endswith("_url") or lowered == "url" or "html_url" in lowered:
        return True
    return any(token in lowered for token in VERBOSE_FIELDS)
