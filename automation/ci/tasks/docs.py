"""The checked-in CLI documentation, regenerated and checked for staleness."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from invoke.exceptions import Exit
from python_codeforge import task

if TYPE_CHECKING:
    from invoke.context import Context

DOCS = Path("docs/cli.md")
GENERATE = "uv run python -m gaxi.docsgen"


def _generated(c: Context) -> str:
    """Render the CLI documentation without importing the package into automation."""
    result = c.run(GENERATE, hide=True)
    return str(result.stdout)


@task
def docs(c: Context) -> None:
    """Regenerate the checked-in CLI documentation."""
    DOCS.write_text(_generated(c), encoding="utf-8")
    print(f"wrote {DOCS}")


@task(name="docs-check")
def docs_check(c: Context) -> None:
    """Fail when the checked-in CLI documentation is stale."""
    if DOCS.read_text(encoding="utf-8") != _generated(c):
        msg = f"{DOCS} is stale; run 'uv run invoke docs'"
        raise Exit(msg, code=1)
    print(f"{DOCS} current")
