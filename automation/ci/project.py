"""The project version as `pyproject.toml` declares it.

`pyproject.toml` is the single source: the Nix package reads it, `uv.lock`
records it, and the application reads it back out of the installed metadata.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ci.version import Version

PATH = Path("pyproject.toml")

_VERSION_LINE = re.compile(r'^version = "\d+\.\d+\.\d+"$', re.MULTILINE)


def current_version(text: str) -> Version:
    """The version `pyproject.toml` declares."""
    return Version.parse(str(tomllib.loads(text)["project"]["version"]))


def with_version(text: str, version: Version) -> str:
    """`pyproject.toml` with its project version replaced, formatting untouched."""
    replaced, count = _VERSION_LINE.subn(f'version = "{version}"', text, count=1)
    if count != 1:
        msg = "pyproject.toml has no project version line to replace"
        raise ValueError(msg)
    return replaced
