"""Repository context: remote parsing and read-only discovery."""

import subprocess
import unittest
import unittest.mock
from typing import Any

from gaxi import repo_context
from gaxi.repo_context import RepositoryContext, discover, parse_remote


class RemoteParsingTest(unittest.TestCase):
    def test_user_information_is_dropped_from_an_http_remote(self) -> None:
        remote = parse_remote("origin", "https://bot@gitea.example.com/acme/widgets.git")
        assert remote.host == "gitea.example.com"
        assert remote.origin == "https://gitea.example.com"
        assert remote.full_name == "acme/widgets"

    def test_an_ssh_url_keeps_its_host_and_never_gains_an_origin(self) -> None:
        remote = parse_remote("origin", "ssh://git@gitea.example.com/acme/widgets.git")
        assert (remote.scheme, remote.host, remote.origin) == ("ssh", "gitea.example.com", None)
        assert remote.full_name == "acme/widgets"

    def test_an_unrecognised_remote_parses_to_an_empty_remote(self) -> None:
        remote = parse_remote("weird", "not a url at all")
        assert (remote.scheme, remote.host, remote.owner, remote.repo) == ("", "", "", "")
        assert remote.full_name == ""

    def test_a_path_without_an_owner_yields_no_identity(self) -> None:
        remote = parse_remote("origin", "https://gitea.example.com/widgets.git")
        assert remote.full_name == ""

    def test_a_remote_without_a_host_has_no_origin(self) -> None:
        remote = parse_remote("origin", "https:///acme/widgets.git")
        assert remote.origin is None


class ContextTest(unittest.TestCase):
    def test_an_empty_context_is_outside_a_repository(self) -> None:
        context = RepositoryContext()
        assert context.in_repository is False
        assert context.origin_remote is None
        assert context.remote("origin") is None


class DiscoveryTest(unittest.TestCase):
    def test_no_repository_yields_an_empty_context(self) -> None:
        with unittest.mock.patch.object(repo_context, "_git", return_value=None):
            assert discover("/tmp").in_repository is False  # noqa: S108

    def test_remotes_are_read_once_each(self) -> None:
        listing = (
            "origin\thttps://gitea.example.com/acme/widgets.git (fetch)\n"
            "origin\thttps://gitea.example.com/acme/widgets.git (push)\n"
            "upstream\thttps://gitea.example.com/other/widgets.git (fetch)\n"
            "broken\n"
        )
        answers = ["/repo", "master", listing]
        with unittest.mock.patch.object(repo_context, "_git", side_effect=answers):
            context = discover("/repo")
        assert context.root == "/repo"
        assert context.branch == "master"
        assert [remote.name for remote in context.remotes] == ["origin", "upstream"]
        assert context.origin_remote is not None
        assert context.origin_remote.full_name == "acme/widgets"

    def test_a_missing_git_is_not_a_failure(self) -> None:
        with unittest.mock.patch.object(subprocess, "run", side_effect=OSError("no git")):
            assert repo_context._git(["status"], ".") is None

    def test_a_failing_git_command_reports_nothing(self) -> None:
        completed: Any = subprocess.CompletedProcess(["git"], 1, "", "")
        with unittest.mock.patch.object(subprocess, "run", return_value=completed):
            assert repo_context._git(["status"], ".") is None
