"""gaxi - an AXI bridge for Gitea-compatible instances."""

from functools import cache


@cache
def _resolve_version() -> str:
    """The version recorded in the installed project metadata, or `unknown`."""
    # Deferred: importing `importlib.metadata` costs ~45ms on its own, and only
    # `--version` and the home view ever ask for the answer. Every other command
    # pays nothing, so `import gaxi` stays under a millisecond.
    from importlib.metadata import PackageNotFoundError, version  # noqa: PLC0415

    try:
        return version("gaxi")
    except PackageNotFoundError:
        return "unknown"


def __getattr__(name: str) -> str:
    """Resolve `__version__` on first access rather than on import."""
    if name == "__version__":
        return _resolve_version()
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
