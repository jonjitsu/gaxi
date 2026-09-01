"""The fetch seam: one exchange, classification, and render."""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

from gaxi import invoke
from gaxi.invocation import Fetched
from gaxi.session import Options
from tests.gaxi import support
from tests.gaxi.support import json_response, response, run_cli


class FetchTest(unittest.TestCase):
    def test_fetch_returns_a_classified_response(self) -> None:
        session = support.make_session(responses=[json_response({"login": "alice"})])
        fetched = invoke.fetch(session, "get", "/user", [])
        assert isinstance(fetched, Fetched)
        assert fetched.classification.kind == "object"
        assert fetched.classification.payload == {"login": "alice"}
        assert len(support.recorded(session)) == 1

    def test_a_non_numeric_page_is_ignored_when_classifying(self) -> None:
        binding = unittest.mock.Mock(query=[("page", "abc")])
        assert invoke._page(binding) is None
        binding.query = [("page", "3")]
        assert invoke._page(binding) == 3


class RunRequestTest(unittest.TestCase):
    def test_save_mode_failure_exchanges_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "archive.zip")
            session = support.make_session(
                options=Options(save=path),
                responses=[response(404, b"not found", media_type="application/json")],
            )
            outcome = invoke.run_request(
                session,
                "get",
                "/repos/acme/widgets/archive/main.zip",
                [],
            )
            assert outcome.exit_code == 1
            assert len(support.recorded(session)) == 1

    def test_save_mode_success_still_writes_the_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "archive.zip")
            payload = b"zip-bytes"
            code, _out, session = run_cli(
                ["get", "/repos/acme/widgets/archive/main.zip", "--save", path],
                responses=[response(200, payload, media_type="application/zip")],
            )
            assert code == 0
            assert Path(path).read_bytes() == payload
            assert len(support.recorded(session)) == 1
