"""Promoting the hand-written changelog onto the version being released.

The changelog is never generated. Its entries carry reasoning no commit subject
holds, so a release retitles the unreleased section and opens a fresh empty one
above it; the prose itself is left exactly where the author put it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ci.version import Version

PATH = Path("CHANGELOG.md")
UNRELEASED = "## Unreleased"

_HEADING = re.compile(r"^## ", re.MULTILINE)


class NothingToReleaseError(Exception):
    """The `## Unreleased` section is empty, so there is no release to cut."""


def promote(changelog: str, version: Version) -> str:
    """Retitle the unreleased section as `version` and open an empty one above it."""
    if not has_unreleased(changelog):
        raise NothingToReleaseError
    return changelog.replace(UNRELEASED, f"{UNRELEASED}\n\n## {version}", 1)


def has_unreleased(changelog: str) -> bool:
    """Whether anything sits between the unreleased heading and the next one."""
    return bool(_body_after(changelog, UNRELEASED))


def section(changelog: str, version: Version) -> str:
    """The body of one released section, for a release announcement."""
    return _body_after(changelog, f"## {version}")


def _body_after(changelog: str, heading: str) -> str:
    """Everything between `heading` and the heading that follows it."""
    start = changelog.find(heading)
    if start == -1:
        msg = f"CHANGELOG.md has no {heading!r} heading"
        raise ValueError(msg)
    rest = changelog[start + len(heading):]
    following = _HEADING.search(rest)
    return rest[: following.start() if following else None].strip()
