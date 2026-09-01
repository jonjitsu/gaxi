"""Semantic version arithmetic."""

from __future__ import annotations

import re
from typing import NamedTuple, Self, override

MAJOR, MINOR, PATCH = "major", "minor", "patch"

_SEMVER = re.compile(r"(\d+)\.(\d+)\.(\d+)")


class Version(NamedTuple):
    """A semantic version, without the pre-release and build parts gaxi never uses."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Self:
        """Read `X.Y.Z`, rejecting anything else."""
        match = _SEMVER.fullmatch(text.strip())
        if match is None:
            msg = f"not a version: {text!r}"
            raise ValueError(msg)
        return cls(*(int(part) for part in match.groups()))

    @override
    def __str__(self) -> str:
        """`X.Y.Z`."""
        return f"{self.major}.{self.minor}.{self.patch}"

    def bumped(self, level: str) -> Version:
        """This version moved on by one `major`, `minor`, or `patch` step."""
        if level == MAJOR:
            return Version(self.major + 1, 0, 0)
        if level == MINOR:
            return Version(self.major, self.minor + 1, 0)
        if level == PATCH:
            return Version(self.major, self.minor, self.patch + 1)
        msg = f"not a bump level: {level!r}"
        raise ValueError(msg)
