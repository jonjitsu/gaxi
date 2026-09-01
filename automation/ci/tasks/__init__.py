"""The invoke collection: Codeforge's gate plus this project's own tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from python_codeforge import gates, ns, task

from ci.tasks import docs as docs_tasks
from ci.tasks import release as release_tasks

if TYPE_CHECKING:
    from invoke.context import Context


@task(pre=[gates.check, docs_tasks.docs_check])
def verify(c: Context) -> None:
    """The repository gate: Codeforge's `check` plus documentation freshness."""


ns.add_task(docs_tasks.docs)
ns.add_task(docs_tasks.docs_check)
ns.add_task(release_tasks.release_prepare)
ns.add_task(release_tasks.release_notes)
ns.add_task(verify)

__all__ = ["ns"]
