"""The capability catalog and capability resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from gaxi.errors import GaxiError, UsageError
from gaxi.naming import command
from gaxi.suggestions import build, capabilities, disambiguate
from gaxi.swagger import compile_description

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from gaxi.capability import Capability
    from gaxi.jsonshape import JsonObject
    from gaxi.swagger import Description

type Match = tuple[Capability, dict[str, str]]
MAX_DISAMBIGUATION_HINTS = 3


class Catalog:
    """Every capability advertised by one instance."""

    def __init__(
        self,
        capabilities: Iterable[Capability],
        description: Description,
        origin: str = "",
    ) -> None:
        self.capabilities = list(capabilities)
        self.description = description
        self.origin = origin
        self.by_key = {cap.key: cap for cap in self.capabilities}
        self.by_operation_id: dict[str, Capability] = {}
        for cap in self.capabilities:
            if cap.operation_id:
                self.by_operation_id.setdefault(cap.operation_id, cap)

    @classmethod
    def from_document(cls, raw: JsonObject, origin: str = "") -> Self:
        """Compile one instance description into a catalog."""
        capabilities, description = compile_description(raw)
        return cls(capabilities, description, origin=origin)

    @property
    def base_path(self) -> str:
        """The API base path every request is relative to."""
        return self.description.base_path

    @property
    def server_version(self) -> str:
        """The instance version the description advertises."""
        return self.description.version

    def available(self) -> list[Capability]:
        """Every capability that compiled."""
        return [cap for cap in self.capabilities if cap.available]

    def unavailable(self) -> list[Capability]:
        """Every capability disabled by an unsupported construct."""
        return [cap for cap in self.capabilities if not cap.available]

    def select(self, selector: str) -> Capability:
        """Select one capability by `method:path-template` key or operationId."""
        cap = self.by_key.get(selector) or self.by_operation_id.get(selector)
        if cap is None and ":" in selector:
            method, _, path = selector.partition(":")
            cap = self.by_key.get(f"{method.lower()}:{path}")
        if cap is None:
            msg = f"no capability named {selector}"
            hint = selector.rsplit("/", maxsplit=1)[-1] or selector
            raise GaxiError(
                msg,
                details=[("selector", selector)],
                help_commands=build(capabilities(hint)),
            )
        return cap

    def match(self, method: str, path: str) -> list[Match]:
        """Every capability whose method and path template match a concrete path."""
        matches: list[Match] = []
        for cap in self.capabilities:
            if cap.method != method:
                continue
            found = cap.matcher.match(path)
            if found:
                matches.append((cap, found.groupdict()))
        return matches

    def resolve(self, method: str, path: str, selector: str | None = None) -> Match:
        """Resolve one concrete request to exactly one advertised capability."""
        matches = self.match(method, path)
        if selector:
            return self._selected(method, path, selector, matches)
        if not matches:
            msg = f"no advertised capability for {method.upper()} {path}"
            details = [("request", f"{method.upper()} {path}")]
            without_base = self._without_base_path(method, path)
            if without_base is not None:
                details.append(("base_path", "already implied by the instance"))
            raise GaxiError(
                msg,
                details=details,
                help_commands=build(
                    None if without_base is None else command(method, without_base),
                    capabilities(_search_hint(path)),
                    capabilities(),
                ),
            )
        if len(matches) > 1:
            return _most_specific(method, path, matches)
        return _checked(*matches[0])

    def _without_base_path(self, method: str, path: str) -> str | None:
        """The same path with the instance base path removed, when that would match.

        The description lists paths without the base path, so a caller only arrives
        here carrying one by copying a full URL or a curl line, where it is part of
        the address rather than part of the capability's name.
        """
        base = self.base_path.rstrip("/")
        if not base or not path.startswith(base + "/"):
            return None
        trimmed = path[len(base):]
        return trimmed if self.match(method, trimmed) else None

    def _selected(
        self,
        method: str,
        path: str,
        selector: str,
        matches: Sequence[Match],
    ) -> Match:
        """Resolve against the capability the caller named explicitly."""
        chosen = self.select(selector)
        for cap, values in matches:
            if cap.key == chosen.key:
                return _checked(cap, values)
        msg = f"{selector} does not match {method.upper()} {path}"
        raise UsageError(msg, details=[("capability", chosen.key)])

    def search(self, terms: Iterable[str]) -> list[Capability]:
        """Filter capabilities across method, path, summary, operationId, and tag."""
        results = self.available()
        for term in terms:
            lowered = term.lower()
            results = [cap for cap in results if _matches_term(cap, lowered)]
        return results


def _most_specific(method: str, path: str, matches: Sequence[Match]) -> Match:
    """Choose the single most specific match, or refuse to guess."""
    best = max(cap.specificity for cap, _ in matches)
    finalists = [pair for pair in matches if pair[0].specificity == best]
    if len(finalists) == 1:
        return _checked(*finalists[0])
    keys = sorted(cap.key for cap, _ in finalists)
    msg = f"{len(keys)} capabilities match {method.upper()} {path}"
    raise GaxiError(
        msg,
        details=[("request", f"{method.upper()} {path}")],
        help_commands=build(
            *(disambiguate(method, path, key) for key in keys[:MAX_DISAMBIGUATION_HINTS]),
        ),
    )


def _checked(cap: Capability, values: dict[str, str]) -> Match:
    if not cap.available:
        msg = f"capability {cap.key} is unavailable: {cap.unsupported}"
        raise GaxiError(
            msg,
            details=[("capability", cap.key), ("reason", cap.unsupported or "")],
            help_commands=build(capabilities()),
        )
    return cap, values


def _matches_term(cap: Capability, term: str) -> bool:
    haystack = " ".join(
        [cap.method, cap.path, cap.summary, cap.operation_id, " ".join(cap.tags)],
    ).lower()
    return term in haystack


def _search_hint(path: str) -> str:
    parts = [part for part in path.strip("/").split("/") if part and "{" not in part]
    return parts[-1] if parts else ""
