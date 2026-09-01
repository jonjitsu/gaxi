"""Origin-scoped credential setup.

Tokens are never accepted as command-line arguments and never written to
ordinary configuration; storage and retrieval go through an external credential
helper bound to one exact origin.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from gaxi.config import normalize_origin
from gaxi.credentials import run_helper
from gaxi.document import Aggregate, Document, Lines, Table
from gaxi.errors import GaxiError, UsageError
from gaxi.http import FIRST_SUCCESS
from gaxi.naming import executable
from gaxi.render import status_result
from gaxi.suggestions import (
    auth_add_stdin,
    auth_list,
    build,
    context,
    example_auth_add,
    subcommand_help,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaxi.jsonshape import JsonValue
    from gaxi.session import Session

ACTIONS = ("list", "add", "remove", "allow-insecure")


def run(session: Session, positionals: Sequence[str]) -> Document:
    """Bind, list, or remove the credential for one exact instance origin."""
    action = positionals[0] if positionals else "list"
    if action not in ACTIONS:
        msg = f"unknown auth action {action}"
        raise UsageError(
            msg,
            details=[("known", ", ".join(ACTIONS))],
            help_commands=build(subcommand_help("auth")),
        )
    arguments = positionals[1:]
    if action == "list":
        return _list(session)
    if not arguments:
        msg = f"auth {action} requires an instance origin"
        raise UsageError(
            msg,
            details=[("usage", f"{executable()} auth {action} https://gitea.example.com")],
        )
    origin = normalize_origin(arguments[0])
    if action == "add":
        return _add(session, origin)
    if action == "remove":
        return _remove(session, origin)
    return _allow_insecure(session, origin)


def _list(session: Session) -> Document:
    config = session.config
    rows: list[list[JsonValue]] = []
    for origin, values in sorted(config.servers().items()):
        helper = values.get("credential_helper")
        helper_text = " ".join(helper) if isinstance(helper, list) else (helper or "none")
        rows.append([
            origin,
            "credential-helper" if helper else "none",
            helper_text,
            bool(values.get("insecure_transport")),
        ])
    environment = session.env.get("GITEA_SERVER")
    if environment and session.env.get("GITEA_TOKEN"):
        rows.append([normalize_origin(environment), "environment", "GITEA_TOKEN", False])
    document = Document()
    document.add("count", Aggregate(len(rows), len(rows)))
    document.add("credentials",
                 Table(["origin", "source", "helper", "insecure_transport"], rows))
    document.add("help", Lines(build(example_auth_add())))
    return document


def _helper_for(session: Session, origin: str) -> list[str]:
    option = session.options.helper
    if option:
        return option.split()
    helper = session.config.credential_helper(origin)
    if helper:
        return helper
    msg = "no credential helper is configured for this origin"
    raise GaxiError(
        msg,
        details=[("origin", origin),
                 ("reason", "plaintext tokens are never stored in configuration")],
        help_commands=build(
            f'{executable()} auth add {origin} --token-stdin --helper "<command>"',
        ),
    )


def _add(session: Session, origin: str) -> Document:
    if not session.options.token_stdin:
        msg = "auth add reads the token from stdin; pass --token-stdin"
        raise UsageError(
            msg,
            details=[("origin", origin),
                     ("reason", "tokens are never accepted as command-line arguments")],
            help_commands=build(auth_add_stdin(origin)),
        )
    helper = _helper_for(session, origin)
    token = sys.stdin.read().strip()
    if not token:
        msg = "no token was supplied on stdin"
        raise UsageError(msg,
                         details=[("origin", origin)])
    run_helper(helper, "store", origin, token=token)
    session.config.set_server(origin, {"credential_helper": helper})
    session.config.save()
    return status_result(
        FIRST_SUCCESS,
        "stored",
        extra=[("origin", origin), ("source", "credential-helper")],
        help_commands=build(context(server=origin)),
    )


def _remove(session: Session, origin: str) -> Document:
    helper = _helper_for(session, origin)
    run_helper(helper, "erase", origin)
    return status_result(
        FIRST_SUCCESS,
        "removed",
        extra=[("origin", origin)],
        help_commands=build(auth_list()),
    )


def _allow_insecure(session: Session, origin: str) -> Document:
    if not origin.startswith("http://"):
        msg = "allow-insecure applies only to plaintext HTTP origins"
        raise UsageError(msg, details=[("origin", origin)])
    session.config.set_server(origin, {"insecure_transport": True})
    session.config.save()
    return status_result(
        FIRST_SUCCESS,
        "allowed",
        extra=[("origin", origin), ("insecure_transport", True)],
        help_commands=build(auth_list()),
    )
