"""Reading a bump level out of Conventional Commits subjects."""

import unittest

from ci import commits
from ci.version import MAJOR, MINOR, PATCH


class BumpLevelTest(unittest.TestCase):
    def test_a_feature_is_a_minor_bump(self) -> None:
        assert commits.bump_level(["feat: add a flag"]) == MINOR

    def test_a_fix_is_a_patch_bump(self) -> None:
        assert commits.bump_level(["fix: stop crashing"]) == PATCH

    def test_a_scope_does_not_change_the_level(self) -> None:
        assert commits.bump_level(["feat(cli): add a flag"]) == MINOR

    def test_a_bang_marks_a_breaking_change(self) -> None:
        assert commits.bump_level(["feat!: rename everything"]) == MAJOR
        assert commits.bump_level(["fix(core)!: change the contract"]) == MAJOR

    def test_a_breaking_trailer_marks_a_breaking_change(self) -> None:
        message = "feat: rename everything\n\nBREAKING CHANGE: the old name is gone."
        assert commits.bump_level([message]) == MAJOR

    def test_the_largest_level_across_the_commits_wins(self) -> None:
        assert commits.bump_level(["fix: a", "feat: b", "docs: c"]) == MINOR
        assert commits.bump_level(["fix: a", "feat!: b"]) == MAJOR

    def test_an_untyped_commit_counts_as_a_patch_rather_than_failing(self) -> None:
        assert commits.bump_level(["Read the version from package metadata"]) == PATCH

    def test_a_near_miss_prefix_does_not_read_as_a_feature(self) -> None:
        # `feature:` is not a Conventional Commits type, so it must not bump the minor.
        assert commits.bump_level(["feature: add a flag"]) == PATCH

    def test_a_type_with_no_subject_is_not_a_header(self) -> None:
        assert commits.bump_level(["feat: "]) == PATCH

    def test_no_commits_at_all_is_still_a_patch(self) -> None:
        assert commits.bump_level([]) == PATCH


class UnconventionalTest(unittest.TestCase):
    def test_untyped_subjects_are_reported_so_a_typo_is_visible(self) -> None:
        messages = ["feat: kept", "Read the version\n\nbody", "feature: typo"]
        assert commits.unconventional(messages) == ["Read the version", "feature: typo"]

    def test_a_fully_typed_history_reports_nothing(self) -> None:
        assert commits.unconventional(["feat: a", "ci: b", "chore(deps): c"]) == []


class HistoryTest(unittest.TestCase):
    def test_this_repository_has_a_readable_history(self) -> None:
        assert commits.since(commits.latest_tag()) or commits.latest_tag()
