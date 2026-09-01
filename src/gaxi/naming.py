"""How the bridge refers to itself in generated commands."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

DEFAULT_NAME = "gaxi"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def executable() -> str:
    """The name callers should type, taken from the invoked program."""
    name = os.environ.get("GAXI_EXECUTABLE_NAME")
    if name:
        return name
    candidate = Path(sys.argv[0] or "").name
    usable = bool(NAME_PATTERN.match(candidate)) and not candidate.endswith(".py")
    return candidate if usable else DEFAULT_NAME


def executable_path() -> str:
    """The absolute executable path, abbreviated with `~` in the home directory."""
    override = os.environ.get("GAXI_EXECUTABLE_PATH")
    if override:
        path = override
    elif executable() == DEFAULT_NAME and Path(sys.argv[0] or "").name != DEFAULT_NAME:
        return DEFAULT_NAME
    else:
        path = str(Path(sys.argv[0]).absolute())
    home = str(Path.home())
    if home and path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def quote(value: object) -> str:
    """Quote one assignment value for a copyable command."""
    text = str(value)
    if text and not any(ch.isspace() or ch in "\"'$`\\|&;<>()" for ch in text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def shell_quote(value: object) -> str:
    """Quote one token so a copy-pasted command is safe in a POSIX shell."""
    text = str(value)
    if text and not any(ch.isspace() or ch in "'\"$`\\|&;<>()" for ch in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"


def command(
    method: str,
    path: str,
    assignments: Iterable[tuple[str, object]] = (),
    options: Sequence[str] = (),
) -> str:
    """Build one executable command string."""
    parts = [executable(), method, path]
    parts.extend(f"{name}={quote(value)}" for name, value in assignments)
    parts.extend(options)
    return " ".join(parts)
