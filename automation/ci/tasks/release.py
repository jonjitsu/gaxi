"""Preparing a release: the bump, the changelog promotion, and the notes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from python_codeforge import task

from ci import changelog, commits, project

if TYPE_CHECKING:
    from invoke.context import Context


@task(name="release-prepare")
def release_prepare(c: Context) -> None:
    """Bump the version, retitle the unreleased changelog section, and relock."""
    notes = changelog.PATH.read_text(encoding="utf-8")
    pyproject = project.PATH.read_text(encoding="utf-8")

    # Right after a release lands this is the normal state, not a failure.
    if not changelog.has_unreleased(notes):
        print(f"nothing under '{changelog.UNRELEASED}'; no release to prepare")
        return

    messages = commits.since(commits.latest_tag())
    level = commits.bump_level(messages)
    version = project.current_version(pyproject).bumped(level)

    changelog.PATH.write_text(changelog.promote(notes, version), encoding="utf-8")
    project.PATH.write_text(project.with_version(pyproject, version), encoding="utf-8")
    # The lock records the project's own version, and CI syncs with `--frozen`.
    c.run("uv lock", hide=True)

    for subject in commits.unconventional(messages):
        print(f"note: untyped commit counted as a patch: {subject}")
    print(f"prepared {version} ({level})")


@task(name="release-notes")
def release_notes(c: Context) -> None:  # noqa: ARG001
    """Print the changelog section for the version pyproject currently declares."""
    version = project.current_version(project.PATH.read_text(encoding="utf-8"))
    print(changelog.section(changelog.PATH.read_text(encoding="utf-8"), version))
