"""The live, contextual home view.

The no-argument entry point shows live state, never a usage dump. It is the one
documented exception to the single-request rule: it issues a small, bounded set
of aggregate requests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi.commands import context as context_command
from gaxi.document import UNKNOWN, Document, Lines, Mapping, Scalar
from gaxi.errors import GaxiError
from gaxi.invoke import fetch
from gaxi.naming import command, executable_path
from gaxi.suggestions import auth_add, build, capabilities_placeholder, collect, context

if TYPE_CHECKING:
    from gaxi.classify import Classification
    from gaxi.session import Session

SUMMARY = "Turn a Gitea instance's advertised capabilities into compact, safe requests."


def run(session: Session) -> Document:
    """The live home view: instance state, repository state, next actions."""
    document = Document()
    mapping = Mapping()
    mapping.add("executable", Scalar(executable_path()))
    mapping.add("summary", Scalar(SUMMARY))
    mapping.add("server", Scalar(session.instance.origin))
    mapping.add("version", Scalar(session.instance.version or "unknown"))
    mapping.add("identity", Scalar(_identity(session)))
    full_name = context_command.repository_identity(session)
    if full_name:
        mapping.add("repository", Scalar(full_name))
        mapping.add("branch", Scalar(session.repository.branch or "unknown"))
        mapping.add("open_issues", Scalar(_open_total(session, full_name, "issues")))
        mapping.add("open_pulls", Scalar(_open_total(session, full_name, "pulls")))
    mapping.add("capabilities", Scalar(len(session.catalog.available())))
    document.add("gaxi", mapping)
    document.add("help", Lines(build(*_help(session, full_name))))
    return document


def _identity(session: Session) -> str:
    credential = session.credential
    if credential is None:
        return "anonymous"
    try:
        result = fetch(session, "get", "/user", [])
    except GaxiError:
        return f"credential from {credential.source}"
    classification = result.classification
    if classification.kind == "object" and isinstance(classification.payload, dict):
        login = classification.payload.get("login")
        if login:
            return str(login)
    return f"credential from {credential.source} (unverified)"


def _open_total(session: Session, full_name: str, entity: str) -> int | str:
    """One bounded aggregate request; an unknown total is named, never guessed."""
    path = f"/repos/{full_name}/{entity}"
    assignments = ["state=open", "limit=1"]
    if entity == "issues":
        assignments.append("type=issues")
    try:
        result = fetch(
            session,
            "get",
            path,
            assignments,
            apply_pagination=False,
        )
    except GaxiError:
        return UNKNOWN
    return _collection_count(result.classification)


def _collection_count(classification: Classification) -> int | str:
    if classification.kind != "collection":
        return UNKNOWN
    total = classification.total
    if isinstance(total, int):
        return total
    if total == UNKNOWN:
        return UNKNOWN
    items = classification.payload
    return len(items) if isinstance(items, list) else UNKNOWN


def _help(session: Session, full_name: str) -> list[str]:
    if full_name:
        return collect(
            command("get", f"/repos/{full_name}/issues", [("state", "open")]),
            command("get", f"/repos/{full_name}/pulls", [("state", "open")]),
            capabilities_placeholder(),
        )
    return collect(
        capabilities_placeholder(),
        context(),
        auth_add(session.instance.origin),
    )
