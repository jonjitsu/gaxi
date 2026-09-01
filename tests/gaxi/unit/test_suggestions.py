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
    configure,
    context,
    env_enabled,
    lines,
    prepend,
    root_help,
    suppressed,
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

    def test_env_enabled_recognises_truthy_values(self) -> None:
        assert env_enabled({"GAXI_NO_HELP": "1"})
        assert env_enabled({"GAXI_NO_HELP": "true"})
        assert env_enabled({"GAXI_NO_HELP": "YES"})
        assert not env_enabled({"GAXI_NO_HELP": "0"})
        assert not env_enabled({})

    def test_configure_suppresses_lines_output(self) -> None:
        configure(no_help=True)
        assert suppressed()
        assert lines("gaxi context") is None
        configure(no_help=False)
        assert lines("gaxi context") is not None

    def test_configure_honours_the_environment(self) -> None:
        configure(no_help=False, env={"GAXI_NO_HELP": "on"})
        assert suppressed()
        assert lines("gaxi context") is None
        configure(no_help=False)
