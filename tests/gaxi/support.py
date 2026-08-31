"""Shared helpers: a scripted transport, a session, and CLI capture."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from gaxi import cli
from gaxi.catalog import Catalog
from gaxi.config import Config
from gaxi.discovery import Instance
from gaxi.repo_context import RepositoryContext, parse_remote
from gaxi.session import Options, Session
from gaxi.transport import RecordingTransport, Response
from tests.gaxi.fixtures import DOCUMENT

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from gaxi.jsonshape import JsonObject, JsonValue

STATUS_OK = 200
ORIGIN = "https://gitea.example.com"
REMOTE = "https://gitea.example.com/acme/widgets.git"


def response(
    status: int = STATUS_OK,
    body: bytes | str = b"",
    headers: Mapping[str, str] | None = None,
    media_type: str = "application/json",
) -> Response:
    pairs = [("Content-Type", media_type), *list((headers or {}).items())]
    if isinstance(body, str):
        body = body.encode("utf-8")
    return Response(status, pairs, body=body, url=ORIGIN + "/api/v1/x")


def json_response(
    payload: JsonValue,
    status: int = STATUS_OK,
    headers: Mapping[str, str] | None = None,
) -> Response:
    return response(status, json.dumps(payload), headers)


def repository(remote: str = REMOTE, branch: str = "master") -> RepositoryContext:
    remotes = [parse_remote("origin", remote)] if remote else []
    return RepositoryContext(root="/repo", branch=branch, remotes=remotes)


def make_session(
    responses: Sequence[Response] = (),
    options: Options | None = None,
    env: Mapping[str, str] | None = None,
    config: Config | None = None,
    repo: RepositoryContext | None = None,
    document: JsonObject | None = None,
) -> Session:
    transport = RecordingTransport(responses)
    catalog = Catalog.from_document(document or DOCUMENT, origin=ORIGIN)
    default_config = Config({}, path=Path(tempfile.gettempdir()) / "gaxi-test-config.json")
    return Session(
        options or Options(),
        transport=transport,
        env=env or {},
        config=config or default_config,
        repository=repository() if repo is None else repo,
        instance=Instance(ORIGIN, "repository remote origin", catalog, 0),
    )


def recorded(session: Session) -> list[JsonObject]:
    """The requests the session's scripted transport received."""
    transport = session.transport
    assert isinstance(transport, RecordingTransport)
    return transport.requests


def run_cli(
    argv: Sequence[str],
    session: Session | None = None,
    **kwargs: Any,
) -> tuple[int, str, Session]:
    """Run the CLI and capture stdout; returns `(exit_code, text, session)`."""
    session = session or make_session(**kwargs)
    stream = io.StringIO()
    code = cli.main(argv, session=session, stdout=stream)
    return code, stream.getvalue(), session
