"""Validated invocation: policy checks, the HTTP exchange, and rendering."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urljoin, urlsplit

from gaxi.binding import bind
from gaxi.classify import classify
from gaxi.download import save
from gaxi.errors import GaxiError, UsageError
from gaxi.http import FIRST_FAILURE, FIRST_REDIRECT, FIRST_SUCCESS, parse_int
from gaxi.invocation import Fetched, Invocation, Outcome
from gaxi.naming import command
from gaxi.planner import Planner
from gaxi.render import file_receipt
from gaxi.results import dry_run_document, render_classification
from gaxi.suggestions import build

if TYPE_CHECKING:
    from collections.abc import Mapping as MappingABC
    from collections.abc import Sequence

    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.session import Session
    from gaxi.transport import Response

MAX_REDIRECTS = 5
RETRYABLE = (502, 503, 504)


def _as_api_relative(raw_path: str) -> str:
    """Strip an origin from whatever the caller typed.

    Callers reach for a browser URL or a `host/path` pair; both carry an origin the
    grammar does not take, so the suggestion drops it rather than prefixing a slash.
    """
    split = urlsplit(raw_path)
    if split.scheme and split.netloc:
        path, query = split.path or "/", split.query
    else:
        path, _, query = raw_path.partition("?")
        head, slash, rest = path.partition("/")
        path = "/" + rest if slash and "." in head else "/" + path.lstrip("/")
    return f"{path}?{query}" if query else path


def _suggested_path(session: Session, raw_path: str) -> str:
    """The runnable path a caller most likely meant.

    A pasted URL carries both the origin and the instance base path, and the grammar
    takes neither. The base path is only knowable from the instance, so it is removed
    when the catalog is already reachable and left in place when it is not.
    """
    path = _as_api_relative(raw_path)
    try:
        base = session.catalog.base_path.rstrip("/")
    except GaxiError:
        return path
    return path[len(base) :] if base and path.startswith(base + "/") else path


def run_request(
    session: Session,
    method: str,
    raw_path: str,
    assignments: Sequence[str],
) -> Outcome:
    """Resolve, validate, execute, classify, and render one request."""
    invocation = _resolve_invocation(session, method, raw_path, assignments)
    _check_execution_policy(invocation)
    _check_transport_options(invocation)

    request = session.options.request
    if request.dry_run:
        return Outcome(dry_run_document(invocation))

    response = _exchange(invocation)
    if request.save and FIRST_SUCCESS <= response.status < FIRST_REDIRECT:
        return _save_outcome(invocation, response)
    return _render_exchanged(invocation, response)


def fetch(
    session: Session,
    method: str,
    raw_path: str,
    assignments: Sequence[str],
    *,
    apply_pagination: bool = True,
) -> Fetched:
    """Resolve, validate, exchange, and classify one request."""
    invocation = _resolve_invocation(
        session,
        method,
        raw_path,
        assignments,
        apply_pagination=apply_pagination,
    )
    _check_execution_policy(invocation)
    _check_transport_options(invocation)
    return _fetch_prepared(invocation)


def _resolve_invocation(
    session: Session,
    method: str,
    raw_path: str,
    assignments: Sequence[str],
    *,
    apply_pagination: bool = True,
) -> Invocation:
    request = session.options.request
    method = method.lower()
    path, _, path_query = raw_path.partition("?")
    if not path.startswith("/"):
        msg = f"the API-relative path must begin with '/', got {raw_path!r}"
        raise UsageError(
            msg,
            details=[("path", raw_path), ("expected", "a path relative to the instance")],
            help_commands=build(command(method, _suggested_path(session, raw_path))),
        )
    catalog = session.catalog
    cap, _path_values = catalog.resolve(method, path, request.selector)
    props = session.policy.resolve(cap)
    binding = bind(
        cap,
        assignments,
        path_query,
        request.input_json,
        apply_pagination=apply_pagination,
    )
    planner = Planner(catalog, cap, path, binding, session)
    return Invocation(session, cap, props, binding, planner, method, path)


def _fetch_prepared(invocation: Invocation) -> Fetched:
    response = _exchange(invocation)
    return _classify_response(invocation, response)


def _classify_response(invocation: Invocation, response: Response) -> Fetched:
    page = _page(invocation.binding)
    classification = classify(
        response,
        invocation.props.response or "unknown",
        page=page,
    )
    return Fetched(invocation, classification, response)


def _save_outcome(invocation: Invocation, response: Response) -> Outcome:
    request = invocation.request
    path = request.save or ""
    try:
        receipt = save(response, path, overwrite=invocation.session.options.overwrite)
    except GaxiError as exc:
        if any(name == "reason" and value == "exists" for name, value in exc.details):
            exc.help_commands = build(
                invocation.planner.retry([f"--save {path}", "--overwrite"]),
            )
        raise
    return Outcome(
        file_receipt(receipt.path, receipt.size, receipt.media_type, receipt.sha256),
    )


def _render_exchanged(invocation: Invocation, response: Response) -> Outcome:
    fetched = _classify_response(invocation, response)
    return render_classification(
        fetched.invocation,
        fetched.classification,
        response=fetched.response,
    )


def _page(binding: Binding) -> int | None:
    return parse_int(dict(binding.query).get("page"))


# execution policy ---------------------------------------------------------


def _check_execution_policy(inv: Invocation) -> None:
    cap, props, request = inv.cap, inv.props, inv.request
    if props.effect != "mutate":
        return
    if props.confirmation == "required" and not request.yes:
        msg = f"{cap.key} is a destructive mutation and requires --yes"
        raise GaxiError(
            msg,
            details=[("capability", cap.key), ("confirmation", "required")],
            help_commands=build(inv.planner.retry(["--yes"])),
        )
    if props.confirmation == "unknown" and not request.allow_unknown:
        msg = f"{cap.key} has unknown mutation semantics and requires --allow-unknown"
        raise GaxiError(
            msg,
            details=[
                ("capability", cap.key),
                ("confirmation", "unknown"),
                ("policy_source", props.sources.get("confirmation", "fallback")),
            ],
            help_commands=build(inv.planner.retry(["--allow-unknown"])),
        )


def _check_transport_options(inv: Invocation) -> None:
    request = inv.request
    if inv.props.response == "file" and not (request.save or request.raw):
        msg = f"{inv.cap.key} returns a binary response; use --save <path> or --raw"
        raise UsageError(
            msg,
            details=[("capability", inv.cap.key), ("response", "file")],
            help_commands=build(inv.planner.retry(["--save ./download.bin"])),
        )
    if request.save and request.raw:
        msg = "--save and --raw are mutually exclusive"
        raise UsageError(msg)


# request construction -----------------------------------------------------


def _headers(session: Session, cap: Capability) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if cap.produces:
        headers["Accept"] = ", ".join(cap.produces)
    credential = session.credential
    if credential:
        headers.update(credential.headers())
    return headers


def _encode_body(binding: Binding) -> tuple[bytes | None, str | None]:
    if binding.files:
        return _multipart(binding)
    if binding.form:
        return urlencode(binding.form).encode("utf-8"), "application/x-www-form-urlencoded"
    if binding.body is not None:
        return json.dumps(binding.body).encode("utf-8"), "application/json"
    return None, None


def _multipart(binding: Binding) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = [
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
        for name, value in binding.form
    ]
    for name, path in binding.files:
        filename = Path(path).name
        header = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        parts.append(header + Path(path).read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _exchange(inv: Invocation) -> Response:
    session = inv.session
    url = session.instance.url(inv.path, inv.binding.query_string())
    headers = _headers(session, inv.cap)
    body, content_type = _encode_body(inv.binding)
    if content_type:
        headers["Content-Type"] = content_type
    stream = bool(inv.request.save)
    response = _send_once(inv, url, headers, body, stream=stream)
    return _follow_redirects(inv, response, headers, stream=stream)


def _send_once(
    inv: Invocation,
    url: str,
    headers: MappingABC[str, str],
    body: bytes | None,
    *,
    stream: bool,
) -> Response:
    """Automatic retry is permitted only for `retry: safe`."""
    session, method, props = inv.session, inv.method, inv.props
    try:
        response = session.send(method, url, headers=headers, body=body, stream=stream)
    except GaxiError:
        if props.retry != "safe":
            raise
        session.debug("retrying a safe request after a transport failure")
        return session.send(method, url, headers=headers, body=body, stream=stream)
    if response.status in RETRYABLE and props.retry == "safe":
        session.debug(f"retrying a safe request after status {response.status}")
        return session.send(method, url, headers=headers, body=body, stream=stream)
    return response


def _follow_redirects(
    inv: Invocation,
    response: Response,
    headers: MappingABC[str, str],
    *,
    stream: bool,
) -> Response:
    session = inv.session
    hops = 0
    while (target := _redirect_target(response)) is not None:
        _check_redirect_allowed(inv, response, target)
        hops += 1
        if hops > MAX_REDIRECTS:
            msg = f"redirect limit of {MAX_REDIRECTS} exceeded"
            raise GaxiError(msg, status=response.status, details=[("location", target)])
        forwarded = _forwarded_headers(headers, target, session.instance.origin)
        response = session.send("GET", target, headers=forwarded, stream=stream)
    return response


def _redirect_target(response: Response) -> str | None:
    """Where a redirect points, or None when the response is not a redirect."""
    if not FIRST_REDIRECT <= response.status < FIRST_FAILURE:
        return None
    location = response.headers.get("Location")
    if not location:
        return None
    return urljoin(response.url, location)


def _check_redirect_allowed(inv: Invocation, response: Response, target: str) -> None:
    """A mutation is never redirected, and only GET is ever followed."""
    if inv.props.effect != "mutate":
        return
    msg = "refusing to follow a redirect for a mutation"
    raise GaxiError(
        msg,
        status=response.status,
        request=f"{inv.method.upper()} {response.url}",
        details=[("location", target)],
    )


def _forwarded_headers(
    headers: MappingABC[str, str],
    target: str,
    origin: str,
) -> dict[str, str]:
    """The request headers to carry forward, dropping the credential off-origin."""
    forwarded = dict(headers)
    if not target.startswith(origin):
        forwarded.pop("Authorization", None)
    return forwarded
