"""Logical result documents.

A result is a small ordered document built from a handful of node kinds. Every
output format (TOON, JSON, YAML) encodes the same logical document, so the
rendered shape never depends on the encoder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Iterable

UNKNOWN = "unknown"


class Node:
    """One element of a logical document."""


class Scalar(Node):
    """A single value rendered as `key: value`."""

    def __init__(self, value: object, *, quoted: bool = False) -> None:
        self.value = value
        self.quoted = quoted


class Mapping(Node):
    """An ordered set of key/value pairs rendered under `key:`."""

    def __init__(self, pairs: Iterable[tuple[str, Node]] = ()) -> None:
        self.pairs = list(pairs)

    def add(self, key: str, node: Node | object) -> Self:
        """Append one pair, wrapping a bare value as a `Scalar`."""
        self.pairs.append((key, node if isinstance(node, Node) else Scalar(node)))
        return self


class Table(Node):
    """A named, typed collection rendered as `name[N]{fields}:` plus rows."""

    def __init__(self, fields: Iterable[str], rows: Iterable[Iterable[object]]) -> None:
        self.fields = list(fields)
        self.rows = [list(row) for row in rows]


class Lines(Node):
    """A list of literal strings rendered as `name[N]:` plus `- item` rows."""

    def __init__(self, items: Iterable[str]) -> None:
        self.items = list(items)


class CommaList(Node):
    """A compact comma-separated list rendered as `name[N]: item1, item2`."""

    def __init__(self, items: Iterable[str]) -> None:
        self.items = list(items)


class Aggregate(Node):
    """The pre-computed `count:` aggregate for a collection.

    `total` is an integer when the server total is known, UNKNOWN when the
    response is paginated without a total, and None when it equals `returned`.
    """

    def __init__(self, returned: int, total: int | str | None = None) -> None:
        self.returned = returned
        self.total = total


class Document:
    """An ordered root document."""

    def __init__(self, pairs: Iterable[tuple[str, Node]] = ()) -> None:
        self.pairs = list(pairs)

    def add(self, key: str, node: Node | object) -> Self:
        """Append one top-level pair, wrapping a bare value as a `Scalar`."""
        self.pairs.append((key, node if isinstance(node, Node) else Scalar(node)))
        return self

    def keys(self) -> list[str]:
        """The top-level keys in document order."""
        return [key for key, _ in self.pairs]

    def get(self, key: str) -> Node | None:
        """The first node stored under `key`, or None."""
        for existing, node in self.pairs:
            if existing == key:
                return node
        return None
