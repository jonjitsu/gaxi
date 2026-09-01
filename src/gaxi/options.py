"""Frozen bridge options grouped by the seam that consumes them."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from gaxi.errors import UsageError

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_TIMEOUT = 30
OUTPUT_FORMATS = ("toon", "json", "yaml")
INTEGER_FIELDS = ("timeout", "limit", "page")


@dataclass(frozen=True)
class RequestOptions:
    """Options for resolving, validating, and executing one API request."""

    save: str | None = None
    raw: bool = False
    dry_run: bool = False
    yes: bool = False
    allow_unknown: bool = False
    selector: str | None = None
    input_json: str | None = None
    fields: tuple[str, ...] | None = None
    full: bool = False


@dataclass(frozen=True)
class DiscoveryOptions:
    """Options for instance resolution, catalog loading, and credentials."""

    server: str | None = None
    refresh: bool = False
    debug: bool = False
    timeout: int = DEFAULT_TIMEOUT
    anonymous: bool = False
    limit: int | None = None
    page: int | None = None


@dataclass(frozen=True)
class SetupOptions:
    """Options for writing generated skill or hook files."""

    path: str | None = None


@dataclass(frozen=True)
class OutputOptions:
    """Options for encoding structured results on stdout."""

    format: str = "toon"


@dataclass(frozen=True)
class AuthOptions:
    """Options for credential helper setup."""

    helper: str | None = None
    token_stdin: bool = False


@dataclass(frozen=True)
class Options:
    """Every bridge option, grouped by consumer."""

    request: RequestOptions = field(default_factory=RequestOptions)
    discovery: DiscoveryOptions = field(default_factory=DiscoveryOptions)
    setup: SetupOptions = field(default_factory=SetupOptions)
    output: OutputOptions = field(default_factory=OutputOptions)
    auth: AuthOptions = field(default_factory=AuthOptions)
    no_help: bool = False
    overwrite: bool = False


def build_options(values: Mapping[str, object]) -> Options:
    """Coerce parsed CLI values into a frozen options record."""
    request = RequestOptions(
        save=_optional_str(values.get("save")),
        raw=bool(values.get("raw")),
        dry_run=bool(values.get("dry_run")),
        yes=bool(values.get("yes")),
        allow_unknown=bool(values.get("allow_unknown")),
        selector=_optional_str(values.get("selector")),
        input_json=_coerce_input_json(values.get("input_json")),
        fields=_coerce_fields(values.get("fields")),
        full=bool(values.get("full")),
    )
    discovery = DiscoveryOptions(
        server=_optional_str(values.get("server")),
        refresh=bool(values.get("refresh")),
        debug=bool(values.get("debug")),
        timeout=_positive_int(values.get("timeout", DEFAULT_TIMEOUT), "--timeout"),
        anonymous=bool(values.get("anonymous")),
        limit=_optional_positive_int(values.get("limit"), "--limit"),
        page=_optional_positive_int(values.get("page"), "--page"),
    )
    setup = SetupOptions(
        path=_optional_str(values.get("path")),
    )
    output = OutputOptions(format=_coerce_output(values.get("output", "toon")))
    auth = AuthOptions(
        helper=_optional_str(values.get("helper")),
        token_stdin=bool(values.get("token_stdin")),
    )
    return Options(
        request=request,
        discovery=discovery,
        setup=setup,
        output=output,
        auth=auth,
        no_help=bool(values.get("no_help")),
        overwrite=bool(values.get("overwrite")),
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _coerce_fields(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        return tuple(str(item) for item in value)
    text = str(value)
    fields = tuple(part.strip() for part in text.split(",") if part.strip())
    return fields or None


def _coerce_output(value: object) -> str:
    output = str(value)
    if output in OUTPUT_FORMATS:
        return output
    msg = f"unknown output format {output}"
    raise UsageError(msg, details=[("supported", ", ".join(OUTPUT_FORMATS))])


def _positive_int(value: object, name: str) -> int:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        msg = f"{name} expects an integer, got {value!r}"
        raise UsageError(msg)
    try:
        number = int(value)
    except ValueError as exc:
        msg = f"{name} expects an integer, got {value!r}"
        raise UsageError(msg) from exc
    if number <= 0:
        msg = f"{name} expects a positive integer, got {value!r}"
        raise UsageError(msg)
    return number


def _optional_positive_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, name)


def _coerce_input_json(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if text == "-":
        return sys.stdin.read()
    if text.startswith("@"):
        path = text[1:]
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            msg = f"cannot read --input-json file: {exc}"
            raise UsageError(msg, details=[("path", path)]) from exc
    return text
