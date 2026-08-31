"""The live, contextual home view.

The no-argument entry point shows live state, never a usage dump. It is the one
documented exception to the single-request rule: it issues a small, bounded set
of aggregate requests.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from gaxi.commands import context as context_command
from gaxi.document import Document, Lines, Mapping, Scalar
from gaxi.errors import GaxiError
from gaxi.naming import command, executable, executable_path

if TYPE_CHECKING:
    from gaxi.session import Session

STATUS_OK = 200
UNKNOWN = "unknown"
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
    document.add("help", Lines(_help(session, full_name)))
    return document


def _identity(session: Session) -> str:
    credential = session.credential
    if credential is None:
        return "anonymous"
    try:
        response = session.send(
            "GET",
            session.instance.url("/user"),
            headers=credential.headers(),
        )
    except GaxiError:
        return f"credential from {credential.source}"
    if response.status != STATUS_OK:
        return f"credential from {credential.source} (unverified)"
    try:
        payload = json.loads(response.read_all().decode(response.charset, "replace"))
    except ValueError:
        return f"credential from {credential.source} (unverified)"
    return payload.get("login") or f"credential from {credential.source}"


def _open_total(session: Session, full_name: str, entity: str) -> int | str:
    """One bounded aggregate request; an unknown total is named, never guessed."""
    query = "state=open&limit=1" + ("&type=issues" if entity == "issues" else "")
    url = session.instance.url(f"/repos/{full_name}/{entity}", query)
    headers = {"Accept": "application/json"}
    credential = session.credential
    if credential:
        headers.update(credential.headers())
    try:
        response = session.send("GET", url, headers=headers)
    except GaxiError:
        return UNKNOWN
    if response.status != STATUS_OK:
        return UNKNOWN
    total = response.headers.get("X-Total-Count")
    if total is not None:
        try:
            return int(total)
        except ValueError:
            return UNKNOWN
    try:
        payload = json.loads(response.read_all().decode(response.charset, "replace"))
    except ValueError:
        return UNKNOWN
    return len(payload) if isinstance(payload, list) else UNKNOWN


def _help(session: Session, full_name: str) -> list[str]:
    if full_name:
        return [
            command("get", f"/repos/{full_name}/issues", [("state", "open")]),
            command("get", f"/repos/{full_name}/pulls", [("state", "open")]),
            f"{executable()} capabilities <search terms>",
        ]
    return [
        f"{executable()} capabilities <search terms>",
        f"{executable()} context",
        f"{executable()} auth add {session.instance.origin}",
    ]
