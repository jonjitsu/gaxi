"""The HTTP exchange.

The transport performs exactly one request per call and never follows a
redirect on its own; redirect policy belongs to the invoker so that credentials
can be dropped when the origin changes.
"""

from __future__ import annotations

import http.client
import io
import urllib.error
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Protocol, override, runtime_checkable

from gaxi.errors import GaxiError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from gaxi.jsonshape import JsonObject

USER_AGENT = "gaxi/1.0 (+https://axi.md)"
CHUNK = 65536
ALLOWED_SCHEMES = frozenset({"http", "https"})


@runtime_checkable
class ByteStream(Protocol):
    """The part of a file-like response body the bridge relies on."""

    def read(self, _amt: int = ..., /) -> bytes:
        """Return up to the requested number of bytes, or the whole remainder."""
        ...


class Headers:
    """Case-insensitive response headers preserving their original names."""

    def __init__(self, pairs: Iterable[tuple[str, str]] = ()) -> None:
        self._pairs = list(pairs)
        self._index = {name.lower(): value for name, value in self._pairs}

    def get(self, name: str, default: str | None = None) -> str | None:
        """The value stored under `name`, matched without regard to case."""
        return self._index.get(name.lower(), default)

    def __contains__(self, name: str) -> bool:
        """Whether a header with this name was returned."""
        return name.lower() in self._index

    def items(self) -> list[tuple[str, str]]:
        """The header pairs in their original order and casing."""
        return list(self._pairs)


class Response:
    """One HTTP response."""

    def __init__(
        self,
        status: int,
        headers: Headers | Iterable[tuple[str, str]],
        body: bytes = b"",
        url: str = "",
        *,
        stream: ByteStream | None = None,
        reason: str = "",
    ) -> None:
        self.status = status
        self.headers = headers if isinstance(headers, Headers) else Headers(headers)
        self.body = body
        self.url = url
        self.stream = stream
        self.reason = reason

    @property
    def media_type(self) -> str:
        """The `Content-Type` media type, lowercased and stripped of parameters."""
        value = self.headers.get("Content-Type", "") or ""
        return value.split(";", 1)[0].strip().lower()

    @property
    def charset(self) -> str:
        """The declared response charset, defaulting to UTF-8."""
        value = self.headers.get("Content-Type", "") or ""
        for part in value.split(";")[1:]:
            key, _, encoding = part.strip().partition("=")
            if key.lower() == "charset":
                return encoding.strip("\"'") or "utf-8"
        return "utf-8"

    def read_all(self) -> bytes:
        """Drain any open stream into `body` and return the whole body."""
        if self.stream is not None and not self.body:
            self.body = self.stream.read()
            self.stream = None
        return self.body


@runtime_checkable
class Exchange(Protocol):
    """One request/response round trip, however it is performed."""

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        *,
        stream: bool = False,
    ) -> Response:
        """Perform exactly one request and return its response."""
        ...


class Transport:
    """A single-request urllib transport."""

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect())

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        *,
        stream: bool = False,
    ) -> Response:
        """Perform exactly one request, never following a redirect."""
        scheme = urllib.parse.urlsplit(url).scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            msg = f"refusing to request {scheme or 'a scheme-less URL'}: only http and https"
            raise GaxiError(msg, details=[("request", f"{method.upper()} {url}")])
        request = urllib.request.Request(url, data=body, method=method.upper())  # noqa: S310
        request.add_header("User-Agent", USER_AGENT)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            raw = self._opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            raw = exc
        except urllib.error.URLError as exc:
            msg = f"cannot reach {url}: {_reason(exc)}"
            raise GaxiError(msg, details=[("request", f"{method.upper()} {url}")]) from exc
        except (TimeoutError, http.client.HTTPException, OSError) as exc:
            msg = f"cannot reach {url}: {exc}"
            raise GaxiError(msg, details=[("request", f"{method.upper()} {url}")]) from exc
        headers_out = Headers(raw.headers.items())
        status = raw.status if raw.status is not None else 0
        if stream:
            return Response(status, headers_out, url=url, stream=raw)
        return Response(status, headers_out, body=raw.read(), url=url)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect handler that hands the redirect back to the caller."""

    @override
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        """Never follow a redirect; the invoker decides what a 3xx means."""
        return


class RecordingTransport:
    """A transport that replays scripted responses; used by the test suites."""

    def __init__(self, responses: Iterable[Response] = ()) -> None:
        self.responses = list(responses)
        self.requests: list[JsonObject] = []

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        *,
        stream: bool = False,
    ) -> Response:
        """Return the next scripted response and record what was asked for."""
        self.requests.append({
            "method": method.upper(),
            "url": url,
            "headers": dict(headers or {}),
            "body": body,
        })
        if not self.responses:
            msg = f"no scripted response for {method.upper()} {url}"
            raise GaxiError(msg)
        response = self.responses.pop(0)
        if stream and response.stream is None:
            response.stream = io.BytesIO(response.body)
            response.body = b""
        return response


def _reason(exc: urllib.error.URLError) -> str:
    return str(getattr(exc, "reason", exc))
