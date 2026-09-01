"""Promoting the hand-written changelog onto a version."""

import re
import unittest

import pytest

from ci import changelog
from ci.version import Version

NOTES = """# Changelog

## Unreleased

- Something worth shipping.

## 1.0.0

First implementation.
"""

EMPTY = """# Changelog

## Unreleased

## 1.0.0

First implementation.
"""


class PromoteTest(unittest.TestCase):
    def test_the_unreleased_section_is_retitled_and_a_fresh_one_opened(self) -> None:
        promoted = changelog.promote(NOTES, Version.parse("1.1.0"))
        assert "## Unreleased\n\n## 1.1.0\n\n- Something worth shipping." in promoted
        assert promoted.count("## Unreleased") == 1

    def test_the_prose_is_carried_over_untouched(self) -> None:
        promoted = changelog.promote(NOTES, Version.parse("1.1.0"))
        assert "- Something worth shipping." in promoted
        assert "First implementation." in promoted

    def test_an_empty_unreleased_section_is_not_a_release(self) -> None:
        with pytest.raises(changelog.NothingToReleaseError):
            changelog.promote(EMPTY, Version.parse("1.0.1"))

    def test_a_changelog_without_the_heading_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="no '## Unreleased' heading"):
            changelog.promote("# Changelog\n", Version.parse("1.0.1"))


class SectionTest(unittest.TestCase):
    def test_one_released_section_is_extracted_for_the_announcement(self) -> None:
        promoted = changelog.promote(NOTES, Version.parse("1.1.0"))
        assert changelog.section(promoted, Version.parse("1.1.0")) == "- Something worth shipping."

    def test_the_last_section_runs_to_the_end_of_the_file(self) -> None:
        assert changelog.section(NOTES, Version.parse("1.0.0")) == "First implementation."

    def test_a_missing_section_is_rejected(self) -> None:
        with pytest.raises(ValueError, match=re.escape("no '## 9.9.9' heading")):
            changelog.section(NOTES, Version.parse("9.9.9"))


class RepositoryTest(unittest.TestCase):
    """These must not require pending entries.

    On the release branch `## Unreleased` is empty by construction, and that
    branch has to pass the same gate as every other.
    """

    def test_the_changelog_carries_the_heading_the_release_moves(self) -> None:
        assert changelog.UNRELEASED in changelog.PATH.read_text(encoding="utf-8")
