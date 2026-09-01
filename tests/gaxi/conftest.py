"""Fixtures shared by every ``gaxi`` suite."""

from __future__ import annotations

import pytest

from gaxi.naming import DEFAULT_NAME
from gaxi.suggestions import configure


@pytest.fixture(autouse=True)
def _reset_help_suppression(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep help[] suppression from leaking between tests."""
    monkeypatch.delenv("GAXI_NO_HELP", raising=False)
    configure(no_help=False)


@pytest.fixture(autouse=True)
def _pinned_executable_name(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the self-reference so rendered commands do not name the test runner.

    ``naming.executable`` reads ``sys.argv[0]``, which is the runner under test.
    """
    monkeypatch.setenv("GAXI_EXECUTABLE_NAME", DEFAULT_NAME)
    monkeypatch.setenv("GAXI_EXECUTABLE_PATH", DEFAULT_NAME)
