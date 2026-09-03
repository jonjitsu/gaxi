"""Encoders for logical result documents: TOON (default), JSON, and YAML."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gaxi.document import (
    UNKNOWN,
    Aggregate,
    CommaList,
    Document,
    Lines,
    Mapping,
    Node,
    Scalar,
    Table,
)

if TYPE_CHECKING:
    from gaxi.jsonshape import JsonObject, JsonValue

INDENT = "  "
_AMBIGUOUS = {"true", "false", "null", "-", ""}


def _looks_numeric(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _escape(text: str) -> str:
    out = text.replace("\\", "\\\\").replace('"', '\\"')
    return out.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")


def _needs_quotes(text: str, *, in_row: bool) -> bool:
    if text.strip() != text:
        return True
    if any(ch in text for ch in ('"', "\n", "\r", "\t", ",")):
        return True
    if in_row:
        return False
    if text.lower() in _AMBIGUOUS:
        return True
    return _looks_numeric(text)


def format_value(value: object, *, in_row: bool = False, quoted: bool = False) -> str:
    """Render one scalar as TOON text."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
        return repr(value) if isinstance(value, float) else str(value)
    text = str(value)
    if quoted or _needs_quotes(text, in_row=in_row):
        return '"' + _escape(text) + '"'
    return text


def _aggregate_lines(key: str, node: Aggregate) -> list[str]:
    if node.returned == 0:
        return [f"{key}: 0"]
    if node.total is None:
        return [f"{key}: {node.returned} of {node.returned} total"]
    if node.total == UNKNOWN:
        return [f"{key}: {node.returned}", "total: unknown"]
    return [f"{key}: {node.returned} of {node.total} total"]


def _mapping_lines(key: str, node: Mapping, depth: int) -> list[str]:
    lines = [f"{INDENT * depth}{key}:"]
    for child_key, child in node.pairs:
        lines.extend(_node_lines(child_key, child, depth + 1))
    return lines


def _table_lines(key: str, node: Table, depth: int) -> list[str]:
    pad = INDENT * depth
    fields = ",".join(node.fields)
    lines = [f"{pad}{key}[{len(node.rows)}]{{{fields}}}:"]
    lines.extend(
        f"{pad}{INDENT}" + ",".join(_row_cell(cell) for cell in row)
        for row in node.rows
    )
    return lines


def _item_lines(key: str, node: Lines, depth: int) -> list[str]:
    pad = INDENT * depth
    lines = [f"{pad}{key}[{len(node.items)}]:"]
    lines.extend(f"{pad}{INDENT}- {item}" for item in node.items)
    return lines


def _comma_list_lines(key: str, node: CommaList, depth: int) -> list[str]:
    pad = INDENT * depth
    joined = ", ".join(format_value(item) for item in node.items)
    return [f"{pad}{key}[{len(node.items)}]: {joined}"]


def _node_lines(key: str, node: Node, depth: int) -> list[str]:
    pad = INDENT * depth
    if isinstance(node, Aggregate):
        return [pad + line for line in _aggregate_lines(key, node)]
    if isinstance(node, Scalar):
        return [f"{pad}{key}: {format_value(node.value, quoted=node.quoted)}"]
    if isinstance(node, Mapping):
        return _mapping_lines(key, node, depth)
    if isinstance(node, Table):
        return _table_lines(key, node, depth)
    if isinstance(node, Lines):
        return _item_lines(key, node, depth)
    if isinstance(node, CommaList):
        return _comma_list_lines(key, node, depth)
    msg = f"unsupported node: {type(node).__name__}"
    raise TypeError(msg)


def _row_cell(cell: object) -> str:
    if isinstance(cell, Scalar):
        return format_value(cell.value, in_row=True, quoted=cell.quoted)
    return format_value(cell, in_row=True)


def to_toon(document: Document) -> str:
    """Render the document as TOON, the default output format."""
    lines: list[str] = []
    for key, node in document.pairs:
        lines.extend(_node_lines(key, node, 0))
    return "\n".join(lines)


def _plain_table(node: Table) -> JsonValue:
    return [
        {field: _plain_cell(cell) for field, cell in zip(node.fields, row, strict=False)}
        for row in node.rows
    ]


def _plain(node: Node) -> JsonValue:
    if isinstance(node, Scalar):
        return node.value
    if isinstance(node, Aggregate):
        return node.returned
    if isinstance(node, Mapping):
        return {key: _plain(child) for key, child in node.pairs}
    if isinstance(node, Table):
        return _plain_table(node)
    if isinstance(node, Lines):
        return list(node.items)
    if isinstance(node, CommaList):
        return list(node.items)
    msg = f"unsupported node: {type(node).__name__}"
    raise TypeError(msg)


def _plain_cell(cell: object) -> JsonValue:
    return cell.value if isinstance(cell, Scalar) else cell


def to_object(document: Document) -> JsonObject:
    """The logical document as plain Python data, shared by JSON and YAML."""
    out: JsonObject = {}
    for key, node in document.pairs:
        out[key] = _plain(node)
        if isinstance(node, Aggregate) and node.returned:
            out["total"] = node.returned if node.total is None else node.total
    return out


def to_json(document: Document) -> str:
    """Render the document as indented JSON."""
    return json.dumps(to_object(document), indent=2, ensure_ascii=False)


def _yaml_scalar(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_child(key: str, child: JsonValue, depth: int) -> list[str]:
    pad = INDENT * depth
    if isinstance(child, dict | list):
        if child:
            return [f"{pad}{key}:", *_yaml_lines(child, depth + 1)]
        empty = "{}" if isinstance(child, dict) else "[]"
        return [f"{pad}{key}: {empty}"]
    return [f"{pad}{key}: {_yaml_scalar(child)}"]


def _yaml_item(item: JsonValue, depth: int) -> list[str]:
    pad = INDENT * depth
    if isinstance(item, dict | list) and item:
        inner = _yaml_lines(item, depth + 1)
        return [f"{pad}- {inner[0].strip()}", *inner[1:]]
    return [f"{pad}- {_yaml_scalar(item)}"]


def _yaml_lines(value: JsonValue, depth: int) -> list[str]:
    if isinstance(value, dict):
        lines: list[str] = []
        for key, child in value.items():
            lines.extend(_yaml_child(key, child, depth))
        return lines
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            items.extend(_yaml_item(item, depth))
        return items
    return [f"{INDENT * depth}{_yaml_scalar(value)}"]


def to_yaml(document: Document) -> str:
    """Render the document as YAML."""
    return "\n".join(_yaml_lines(to_object(document), 0))


def encode(document: Document, output_format: str) -> str:
    """Render the document in the named output format."""
    if output_format == "toon":
        return to_toon(document)
    if output_format == "json":
        return to_json(document)
    if output_format == "yaml":
        return to_yaml(document)
    msg = f"unknown output format: {output_format}"
    raise ValueError(msg)
