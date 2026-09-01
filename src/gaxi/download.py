"""Download a response body to disk and return a receipt.

Streaming, digesting, and atomic replace live here so result shaping stays
focused on classified responses.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from gaxi.errors import GaxiError
from gaxi.transport import CHUNK

if TYPE_CHECKING:
    from gaxi.transport import ByteStream, Response


class _Digest(Protocol):
    def update(self, data: bytes, /) -> None:
        """Add more bytes to the running digest."""
        ...

    def hexdigest(self) -> str:
        """The digest so far, as hexadecimal."""
        ...


@dataclass(frozen=True, slots=True)
class Receipt:
    """What was written when a response body was saved to disk."""

    path: str
    size: int
    media_type: str
    sha256: str


class _BufferedBody:
    """Adapter for a body already held in memory."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def write_to(self, destination: Path, digest: _Digest) -> int:
        """Write the whole body to `destination`, hashing it on the way through."""
        digest.update(self._body)
        with destination.open("wb") as handle:
            handle.write(self._body)
        return len(self._body)


class _StreamedBody:
    """Adapter for a response body read incrementally from a stream."""

    def __init__(self, stream: ByteStream) -> None:
        self._stream = stream

    def write_to(self, destination: Path, digest: _Digest) -> int:
        """Stream the body to `destination`, hashing it on the way through."""
        size = 0
        with destination.open("wb") as handle:
            while chunk := self._stream.read(CHUNK):
                digest.update(chunk)
                size += len(chunk)
                handle.write(chunk)
        return size


def save(response: Response, path: str, *, overwrite: bool = False) -> Receipt:
    """Stream `response` to `path` and return a receipt for what was written."""
    destination = Path(path).absolute()
    if destination.exists() and not overwrite:
        msg = f"{path} already exists"
        raise GaxiError(msg, details=[("path", path), ("reason", "exists")])
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".gaxi-{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    adapter = _body_adapter(response)
    try:
        size = adapter.write_to(temporary, digest)
        temporary.replace(destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        msg = f"cannot save response: {exc}"
        raise GaxiError(msg, details=[("path", path)]) from exc
    return Receipt(
        path=path,
        size=size,
        media_type=response.media_type or "application/octet-stream",
        sha256=digest.hexdigest(),
    )


def _body_adapter(response: Response) -> _BufferedBody | _StreamedBody:
    """The adapter that matches how this response exposes its body."""
    if response.stream is None:
        return _BufferedBody(response.read_all())
    return _StreamedBody(response.stream)
