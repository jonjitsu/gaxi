"""Repository context.

Ambient owner, repository, and origin values are derived from the current Git
repository's remotes. Git configuration is read, never modified, and repository
content is never a source of credentials.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  (git is read through its own command)
from typing import TYPE_CHECKING

from gaxi.config import normalize_origin

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

SSH_SHORTHAND = re.compile(r"^(?:(?P<user>[^@/]+)@)?(?P<host>[^:/]+):(?P<path>.+)$")
REMOTE_FIELDS = 2
OWNER_AND_REPO = 2


class Remote:
    """One parsed Git remote."""

    def __init__(
        self,
        name: str,
        url: str,
        scheme: str,
        host: str,
        owner: str,
        repo: str,
        origin: str | None = None,
    ) -> None:
        self.name = name
        self.url = url
        self.scheme = scheme
        self.host = host
        self.owner = owner
        self.repo = repo
        self.origin = origin

    @property
    def full_name(self) -> str:
        """The `owner/repo` identity, or an empty string when either is unknown."""
        return f"{self.owner}/{self.repo}" if self.owner and self.repo else ""


class RepositoryContext:
    """The ambient repository context, or an empty context outside a repository."""

    def __init__(
        self,
        root: str | None = None,
        branch: str | None = None,
        remotes: Iterable[Remote] = (),
    ) -> None:
        self.root = root
        self.branch = branch
        self.remotes = list(remotes)

    @property
    def in_repository(self) -> bool:
        """Whether the bridge was invoked inside a Git repository."""
        return bool(self.root)

    def remote(self, name: str) -> Remote | None:
        """The parsed remote of this name, or None."""
        for remote in self.remotes:
            if remote.name == name:
                return remote
        return None

    @property
    def origin_remote(self) -> Remote | None:
        """The `origin` remote, or None."""
        return self.remote("origin")


def _git(args: Sequence[str], cwd: str) -> str | None:
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603 B607
            ["git", *args],  # noqa: S607  (resolved through PATH)
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, ValueError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def parse_remote(name: str, url: str) -> Remote:
    """Parse a Git remote URL into scheme, host, owner, and repository."""
    text = url.strip()
    if text.startswith(("http://", "https://")):
        scheme, _, rest = text.partition("://")
        netloc, _, path = rest.partition("/")
        netloc = netloc.rsplit("@", 1)[-1]
        owner, repo = _owner_repo(path)
        origin = normalize_origin(f"{scheme}://{netloc}") if netloc else None
        return Remote(name, url, scheme, netloc, owner, repo, origin)
    if text.startswith("ssh://"):
        rest = text[len("ssh://"):]
        netloc, _, path = rest.partition("/")
        host = netloc.rsplit("@", 1)[-1]
        owner, repo = _owner_repo(path)
        return Remote(name, url, "ssh", host, owner, repo, None)
    match = SSH_SHORTHAND.match(text)
    if match:
        owner, repo = _owner_repo(match.group("path"))
        return Remote(name, url, "ssh", match.group("host"), owner, repo, None)
    return Remote(name, url, "", "", "", "", None)


def _owner_repo(path: str) -> tuple[str, str]:
    parts = [part for part in path.strip("/").split("/") if part]
    if len(parts) < OWNER_AND_REPO:
        return "", ""
    owner, repo = parts[-2], parts[-1]
    repo = repo.removesuffix(".git")
    return owner, repo


def discover(cwd: str = ".") -> RepositoryContext:
    """Read the ambient repository context without modifying the repository."""
    root = _git(["rev-parse", "--show-toplevel"], cwd)
    if not root:
        return RepositoryContext()
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    listing = _git(["remote", "-v"], cwd) or ""
    remotes: dict[str, Remote] = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= REMOTE_FIELDS and parts[0] not in remotes:
            remotes[parts[0]] = parse_remote(parts[0], parts[1])
    return RepositoryContext(root=root, branch=branch, remotes=list(remotes.values()))
