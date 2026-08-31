"""What the bridge suggests when a caller names a path the wrong way."""

import unittest

import pytest

from gaxi.catalog import Catalog
from gaxi.errors import EXIT_FAILURE, EXIT_USAGE, GaxiError
from gaxi.invoke import _as_api_relative
from gaxi.session import Options, Session
from gaxi.transport import RecordingTransport
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT
from tests.gaxi.support import run_cli

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)


class ApiRelativeTest(unittest.TestCase):
    def test_a_pasted_url_loses_its_origin(self) -> None:
        assert _as_api_relative("https://gitea.example.com/api/v1/user") == "/api/v1/user"

    def test_a_url_keeps_its_query(self) -> None:
        assert _as_api_relative("https://gitea.example.com/api/v1/x?q=1") == "/api/v1/x?q=1"

    def test_a_bare_origin_becomes_the_root(self) -> None:
        assert _as_api_relative("https://gitea.example.com") == "/"

    def test_a_scheme_less_host_loses_its_origin_too(self) -> None:
        assert _as_api_relative("gitea.example.com/api/v1/user") == "/api/v1/user"
        assert _as_api_relative("gitea.example.com/x?q=1") == "/x?q=1"

    def test_a_path_that_merely_lost_its_slash_keeps_every_segment(self) -> None:
        assert _as_api_relative("repos/acme/widgets/pulls") == "/repos/acme/widgets/pulls"
        assert _as_api_relative("user") == "/user"


class UrlInsteadOfPathTest(unittest.TestCase):
    def test_a_pasted_url_is_refused_with_a_directly_runnable_command(self) -> None:
        code, out, _ = run_cli(["get", support.ORIGIN + "/api/v1/repos/acme/widgets/pulls"])
        assert code == EXIT_USAGE
        assert "must begin with '/'" in out
        assert "- gaxi get /repos/acme/widgets/pulls" in out
        assert "/https:" not in out

    def test_the_base_path_stays_when_the_instance_cannot_be_reached(self) -> None:
        session = Session(Options(server=support.ORIGIN), transport=RecordingTransport())
        code, out, _ = run_cli(
            ["get", support.ORIGIN + "/api/v1/user"], session=session,
        )
        assert code == EXIT_USAGE
        assert "- gaxi get /api/v1/user" in out


class BasePathTest(unittest.TestCase):
    def test_the_base_path_prefix_is_named_as_the_reason(self) -> None:
        code, out, _ = run_cli(["get", "/api/v1/repos/acme/widgets/pulls"])
        assert code == EXIT_FAILURE
        assert "no advertised capability" in out
        assert "base_path: already implied by the instance" in out
        assert "- gaxi get /repos/acme/widgets/pulls" in out

    def test_a_prefix_that_still_matches_nothing_is_not_suggested(self) -> None:
        with pytest.raises(GaxiError) as caught:
            CATALOG.resolve("get", "/api/v1/nothing/here")
        assert caught.value.details == [("request", "GET /api/v1/nothing/here")]
        assert caught.value.help_commands[0].startswith("gaxi capabilities")

    def test_an_instance_with_no_base_path_suggests_nothing_extra(self) -> None:
        raw = {"swagger": "2.0", "paths": {"/things": {"get": {}}}}
        catalog = Catalog.from_document(raw, origin=support.ORIGIN)
        assert catalog.base_path == "/"
        with pytest.raises(GaxiError) as caught:
            catalog.resolve("get", "/absent")
        assert len(caught.value.help_commands) == 2
