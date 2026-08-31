"""Result shapes for the responses the ordinary suites do not exercise."""

import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

from gaxi import invoke, results
from gaxi.catalog import Catalog
from gaxi.document import Document, Mapping, Scalar, Table
from gaxi.encode import to_toon
from gaxi.errors import EXIT_USAGE
from gaxi.render import redirect
from gaxi.repo_context import RepositoryContext
from gaxi.session import Options
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT
from tests.gaxi.support import json_response, response, run_cli

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)


class RedirectTest(unittest.TestCase):
    def test_a_redirect_the_bridge_did_not_follow_is_reported(self) -> None:
        document = redirect(302, "https://gitea.example.com/elsewhere")
        rendered = to_toon(document)
        assert "redirect:" in rendered
        assert "  status: 302" in rendered
        assert "  location: https://gitea.example.com/elsewhere" in rendered


class ErrorMessageTest(unittest.TestCase):
    def test_a_list_of_errors_is_joined(self) -> None:
        failure = json_response({"errors": ["first", "second", "third", "fourth"]}, status=422)
        code, out, _ = run_cli(["get", "/repos/acme/widgets/pulls"], responses=[failure])
        assert code == 1
        assert "  message: first; second; third" in out
        assert "fourth" not in out

    def test_a_payload_without_a_message_falls_back_to_the_status(self) -> None:
        failure = json_response({"other": 1}, status=500)
        code, out, _ = run_cli(["get", "/repos/acme/widgets/pulls"], responses=[failure])
        assert code == 1
        assert "  message: request failed with status 500" in out


class SaveTest(unittest.TestCase):
    def test_a_streamed_body_is_hashed_while_it_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "archive.zip")
            payload = b"x" * 200_000
            code, out, _ = run_cli(
                ["get", "/repos/acme/widgets/archive/main.zip", "--save", path],
                responses=[response(200, payload, media_type="application/zip")],
            )
            assert code == 0
            assert f"  size: {len(payload)}" in out
            assert Path(path).read_bytes() == payload

    def test_an_unwritable_destination_is_a_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "archive.zip")
            with unittest.mock.patch.object(Path, "open", side_effect=OSError("read-only")):
                code, out, _ = run_cli(
                    ["get", "/repos/acme/widgets/archive/main.zip", "--save", path],
                    responses=[response(200, b"x", media_type="application/zip")],
                )
            assert code == 1
            assert "cannot save response" in out

    def test_save_and_raw_are_mutually_exclusive(self) -> None:
        code, out, _ = run_cli(
            ["get", "/repos/acme/widgets/pulls", "--save", "x", "--raw"],
            responses=[json_response([])],
        )
        assert code == EXIT_USAGE
        assert "--save and --raw are mutually exclusive" in out


class ProjectionFallbackTest(unittest.TestCase):
    def test_an_empty_collection_falls_back_to_declared_names(self) -> None:
        code, out, _ = run_cli(
            ["get", "/repos/acme/widgets/pulls"], responses=[json_response([])],
        )
        assert code == 0
        assert "count: 0" in out
        assert "pull_requests[0]{" in out


class DryRunTest(unittest.TestCase):
    def test_body_assignments_appear_in_the_input_table(self) -> None:
        code, out, _ = run_cli(
            ["post", "/repos/acme/widgets/issues", "title=Ship", "--dry-run", "--allow-unknown"],
        )
        assert code == 0
        assert "  sent: false" in out
        assert "title,body," in out or "  title,body," in out

    def test_a_dry_run_outside_a_repository_names_no_repository(self) -> None:
        code, out, _ = run_cli(
            ["get", "/repos/acme/widgets/pulls", "--dry-run"],
            repo=RepositoryContext(),
            options=Options(dry_run=True),
        )
        assert code == 0
        assert "  repository:" not in out


class PageParsingTest(unittest.TestCase):
    def test_a_non_numeric_page_is_ignored(self) -> None:
        assert results._int("abc") is None
        assert results._int(None) is None
        assert results._int("3") == 3


class MultipartTest(unittest.TestCase):
    def test_form_only_bodies_are_url_encoded(self) -> None:
        binding: Any = unittest.mock.Mock(files=[], form=[("name", "asset")], body=None)
        body, content_type = invoke._encode_body(binding)
        assert body == b"name=asset"
        assert content_type == "application/x-www-form-urlencoded"


class DocumentShapeTest(unittest.TestCase):
    def test_a_table_of_inputs_renders_every_location(self) -> None:
        document = Document().add("inputs", Table(["a"], [[1]])).add("x", Mapping())
        assert isinstance(document.get("inputs"), Table)
        assert isinstance(Scalar(1), Scalar)
