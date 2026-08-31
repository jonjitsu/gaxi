"""Structured failures.

Every failure reaches the caller as a structured document on stdout. Exit code
1 marks an ordinary failure; exit code 2 marks an unknown command, an unknown
option, or input that failed validation before any request was sent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


class GaxiError(Exception):
    """A failure that renders as an `error:` document."""

    default_exit_code = EXIT_FAILURE

    def __init__(
        self,
        message: str,
        *,
        exit_code: int | None = None,
        status: int | None = None,
        request: str | None = None,
        details: Iterable[tuple[str, str]] = (),
        help_commands: Iterable[str] = (),
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = self.default_exit_code if exit_code is None else exit_code
        self.status = status
        self.request = request
        self.details = list(details)
        self.help_commands = list(help_commands)


class UsageError(GaxiError):
    """Input the bridge rejected before contacting the instance."""

    default_exit_code = EXIT_USAGE
