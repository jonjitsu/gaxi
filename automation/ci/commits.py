"""What the commits since the last tag ask the version to do.

Only the bump level is inferred from history. The changelog prose is written by
hand as work lands, so nothing here reads a commit body for anything but its
Conventional Commits type.
"""

from __future__ import annotations

import re
import subprocess

from ci.version import MAJOR, MINOR, PATCH

# `type(scope)!: subject`. Only the type and the bang carry a bump level.
_HEADER = re.compile(r"\A(?P<type>[a-z]+)(?:\([^)]*\))?(?P<breaking>!)?: .")
_BREAKING_TRAILER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)

# The Conventional Commits types this project recognises. Anything else is
# reported rather than silently counted as a patch, so `feature:` for `feat:`
# cannot quietly cost a minor bump.
TYPES = frozenset({
    "build", "chore", "ci", "docs", "feat", "fix",
    "perf", "refactor", "revert", "style", "test",
})


def bump_level(messages: list[str]) -> str:
    """The largest bump the commit messages call for; anything unmarked is a patch."""
    levels = {_message_level(message) for message in messages}
    if MAJOR in levels:
        return MAJOR
    if MINOR in levels:
        return MINOR
    return PATCH


def _message_level(message: str) -> str:
    """The bump one commit message asks for."""
    header = _HEADER.match(message)
    if header is None or header["type"] not in TYPES:
        return PATCH
    if header["breaking"] or _BREAKING_TRAILER.search(message):
        return MAJOR
    return MINOR if header["type"] == "feat" else PATCH


def unconventional(messages: list[str]) -> list[str]:
    """The subjects carrying no recognised type, so they read as patches by default."""
    return [message.splitlines()[0] for message in messages if not _typed(message)]


def _typed(message: str) -> bool:
    """Whether a message opens with a type this project recognises."""
    header = _HEADER.match(message)
    return header is not None and header["type"] in TYPES


def since(ref: str | None) -> list[str]:
    """Every commit message after `ref`, or the whole history when there is no tag."""
    span = f"{ref}..HEAD" if ref else "HEAD"
    # A NUL separator keeps multi-paragraph bodies intact.
    out = subprocess.run(  # noqa: S603
        ["git", "log", "--no-merges", "--format=%B%x00", span],  # noqa: S607
        capture_output=True, text=True, check=True,
    ).stdout
    return [chunk.strip() for chunk in out.split("\0") if chunk.strip()]


def latest_tag() -> str | None:
    """The most recent tag reachable from HEAD, or `None` on an untagged history."""
    found = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],  # noqa: S607
        capture_output=True, text=True, check=False,
    )
    return found.stdout.strip() or None
