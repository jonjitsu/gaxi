"""One resolved request, and what running it produced.

Both the invoker and the result shaper need these two values, so they live
apart from either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gaxi.binding import Binding
    from gaxi.capability import Capability
    from gaxi.document import Document
    from gaxi.planner import Planner
    from gaxi.policy import Properties
    from gaxi.session import Options, Session


class Outcome:
    """What a command produced: a document, or exact bytes for `--raw`."""

    def __init__(
        self,
        document: Document | None = None,
        raw: bytes | None = None,
        exit_code: int = 0,
    ) -> None:
        self.document = document
        self.raw = raw
        self.exit_code = exit_code


@dataclass(frozen=True)
class Invocation:
    """One resolved request: what it addresses and what policy says about it."""

    session: Session
    cap: Capability
    props: Properties
    binding: Binding
    planner: Planner
    method: str
    path: str

    @property
    def options(self) -> Options:
        """The options this invocation was given."""
        return self.session.options

    @property
    def request_line(self) -> str:
        """The request as it is reported in results and failures."""
        return f"{self.method.upper()} {self.path}"
