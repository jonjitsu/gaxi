"""Compact ambient context, emitted before an agent acts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi.document import Document, Lines, Mapping, Scalar
from gaxi.naming import command, executable, executable_path

if TYPE_CHECKING:
    from gaxi.session import Session

SEARCH_LIMIT = 20


def repository_identity(session: Session) -> str:
    """The `owner/repo` identity of the ambient repository, if there is one."""
    remote = session.repository.origin_remote if session.repository.in_repository else None
    if remote is None and session.repository.in_repository:
        remote = session.repository.remotes[0] if session.repository.remotes else None
    return remote.full_name if remote and remote.full_name else ""


def run(session: Session) -> Document:
    """The compact ambient context document."""
    document = Document()
    mapping = Mapping()
    mapping.add("executable", Scalar(executable_path()))
    mapping.add("server", Scalar(session.instance.origin))
    mapping.add("server_source", Scalar(session.instance.source))
    mapping.add("version", Scalar(session.instance.version or "unknown"))
    full_name = repository_identity(session)
    mapping.add("repository", Scalar(full_name or "none"))
    mapping.add("branch", Scalar(session.repository.branch or "none"))
    credential = session.credential
    mapping.add("credential", Scalar(credential.source if credential else "anonymous"))
    mapping.add("capabilities", Scalar(len(session.catalog.available())))
    document.add("context", mapping)
    document.add("commands", Lines(command_templates(full_name)))
    return document


def command_templates(full_name: str) -> list[str]:
    """High-value command templates carrying the current repository context."""
    templates = [f"{executable()} capabilities <search terms>"]
    if full_name:
        templates.extend([
            command("get", f"/repos/{full_name}/issues", [("state", "open")]),
            command("get", f"/repos/{full_name}/pulls", [("state", "open")]),
            command("get", f"/repos/{full_name}/issues/<index>"),
        ])
    else:
        templates.extend([
            command("get", "/repos/search", [("limit", SEARCH_LIMIT)]),
            f"{executable()} capability <key|operationId>",
        ])
    return templates
