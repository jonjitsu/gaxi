"""Tests for contextual disclosure at the suggestions interface."""

import unittest
import unittest.mock

from gaxi.document import Lines
from gaxi.suggestions import (
    MAX_SUGGESTIONS,
    auth_add,
    build,
    capabilities,
    capability,
    collect,
    context,
    lines,
    prepend,
    root_help,
)


class SuggestionsTest(unittest.TestCase):
    def test_build_deduplicates_while_preserving_order(self) -> None:
        assert build("one", "two", "one", "three") == ["one", "two", "three"]

    def test_build_ignores_empty_values(self) -> None:
        assert build(None, "", "gaxi context") == ["gaxi context"]

    def test_build_caps_at_max_suggestions(self) -> None:
        commands = [f"cmd-{index}" for index in range(MAX_SUGGESTIONS + 2)]
        assert len(build(*commands)) == MAX_SUGGESTIONS
        assert build(*commands) == commands[:MAX_SUGGESTIONS]

    def test_collect_does_not_cap(self) -> None:
        commands = [f"cmd-{index}" for index in range(MAX_SUGGESTIONS + 2)]
        assert len(collect(*commands)) == MAX_SUGGESTIONS + 2

    def test_prepend_places_one_suggestion_first(self) -> None:
        assert prepend("first", "second", "third") == ["first", "second", "third"]

    def test_lines_returns_none_for_an_empty_result(self) -> None:
        assert lines() is None
        assert lines(None, "") is None

    def test_lines_renders_capped_suggestions(self) -> None:
        rendered = lines("one", "two", "one", "three", "four")
        assert isinstance(rendered, Lines)
        assert rendered.items == ["one", "two", "three"]

    def test_intents_render_through_executable(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"GAXI_EXECUTABLE_NAME": "bridge"}):
            assert root_help() == "bridge --help"
            assert capability("repoListIssues") == "bridge capability repoListIssues"
            assert capabilities("issue", page=2) == "bridge capabilities issue --page 2"
            assert context() == "bridge context"
            assert context(server="https://gitea.example.com") == (
                "bridge --server https://gitea.example.com context"
            )
            assert auth_add("https://gitea.example.com") == (
                "bridge auth add https://gitea.example.com"
            )
