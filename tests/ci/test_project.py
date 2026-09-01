"""The project version as pyproject.toml declares it."""

import unittest

import pytest

from ci import changelog, project
from ci.version import Version

PYPROJECT = '[project]\nversion = "1.2.3"\n\n[tool.ruff]\ntarget-version = "py313"\n'


class VersionLineTest(unittest.TestCase):
    def test_the_project_version_is_read_from_the_project_table(self) -> None:
        assert str(project.current_version(PYPROJECT)) == "1.2.3"

    def test_only_the_project_version_line_is_rewritten(self) -> None:
        rewritten = project.with_version(PYPROJECT, Version.parse("2.0.0"))
        assert 'version = "2.0.0"' in rewritten
        assert 'target-version = "py313"' in rewritten

    def test_a_file_with_no_version_line_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="no project version line"):
            project.with_version('[project]\nname = "gaxi"\n', Version.parse("1.0.0"))


class RepositoryTest(unittest.TestCase):
    def test_the_released_version_has_a_changelog_section(self) -> None:
        version = project.current_version(project.PATH.read_text(encoding="utf-8"))
        assert changelog.section(changelog.PATH.read_text(encoding="utf-8"), version)

    def test_the_project_version_can_be_rewritten_in_place(self) -> None:
        bumped = project.with_version(project.PATH.read_text(encoding="utf-8"),
                                      Version.parse("9.9.9"))
        assert str(project.current_version(bumped)) == "9.9.9"
