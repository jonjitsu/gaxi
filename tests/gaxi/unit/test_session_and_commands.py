"""Session resolution, capability detail, setup, and next-action planning."""

import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from collections.abc import Mapping
from pathlib import Path

import pytest

from gaxi import repo_context as repo_context_module
from gaxi import session as session_module
from gaxi.catalog import Catalog
from gaxi.config import Config
from gaxi.errors import EXIT_USAGE, GaxiError
from gaxi.options import DiscoveryOptions, Options
from gaxi.projection import cell_value, resolve_path, validate_fields
from gaxi.repo_context import RepositoryContext, parse_remote
from gaxi.session import Session
from gaxi.transport import RecordingTransport, Response
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT
from tests.gaxi.support import json_response, response, run_cli

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)


class SessionTest(unittest.TestCase):
    def test_lazy_state_is_resolved_once_and_reused(self) -> None:
        instance = unittest.mock.Mock(origin=support.ORIGIN, source="option", catalog=CATALOG)
        with unittest.mock.patch.object(
            session_module, "resolve_origin", return_value=(support.ORIGIN, "option"),
        ) as resolve, unittest.mock.patch.object(
            session_module, "load_catalog", return_value=(CATALOG, 1),
        ) as load, unittest.mock.patch.object(
            repo_context_module, "discover", return_value=RepositoryContext(),
        ), unittest.mock.patch.object(
            Config, "load", return_value=Config({}),
        ):
            session = Session(Options())
            assert session.instance.origin == support.ORIGIN
            assert session.instance is instance or session.catalog is CATALOG
            assert session.requests == 1
            assert session.config.data == {}
            assert session.repository.in_repository is False
        assert resolve.call_count == 1
        assert load.call_count == 1

    def test_debug_writes_to_stderr_and_redacts(self) -> None:
        session = support.make_session(
            env={"GITEA_TOKEN": "secret"},
            options=Options(discovery=DiscoveryOptions(debug=True)),
        )
        stream = io.StringIO()
        original, sys.stderr = sys.stderr, stream
        try:
            session.debug("token secret leaked")
        finally:
            sys.stderr = original
        assert "secret" not in stream.getvalue()
        assert "<redacted>" in stream.getvalue()

    def test_debug_is_silent_when_it_is_not_asked_for(self) -> None:
        session = support.make_session()
        stream = io.StringIO()
        original, sys.stderr = sys.stderr, stream
        try:
            session.debug("quiet")
        finally:
            sys.stderr = original
        assert stream.getvalue() == ""

    def test_debug_logging_names_the_request(self) -> None:
        session = support.make_session(
            responses=[json_response({})],
            options=Options(discovery=DiscoveryOptions(debug=True)),
        )
        stream = io.StringIO()
        original, sys.stderr = sys.stderr, stream
        try:
            session.send("get", "https://gitea.example.com/api/v1/user")
        finally:
            sys.stderr = original
        assert "GET https://gitea.example.com/api/v1/user" in stream.getvalue()

    def test_debug_logs_catalog_discovery_requests(self) -> None:
        page = Response(
            200,
            [("Content-Type", "text/html")],
            b'<div data-source="/swagger.v1.json"></div>',
        )
        document = Response(
            200,
            [("Content-Type", "application/json")],
            json.dumps(DOCUMENT).encode("utf-8"),
        )
        session = Session(
            Options(discovery=DiscoveryOptions(debug=True, refresh=True)),
            transport=RecordingTransport([page, document]),
            env={"GITEA_SERVER": support.ORIGIN},
            config=Config({}),
            repository=RepositoryContext(),
        )
        stream = io.StringIO()
        original, sys.stderr = sys.stderr, stream
        try:
            assert session.instance.origin == support.ORIGIN
        finally:
            sys.stderr = original
        output = stream.getvalue()
        assert "GET https://gitea.example.com/api/swagger" in output
        assert "GET https://gitea.example.com/swagger.v1.json" in output


class CatalogSelectionTest(unittest.TestCase):
    def test_a_selector_is_matched_case_insensitively_by_method(self) -> None:
        cap = CATALOG.select("GET:/repos/{owner}/{repo}/pulls")
        assert cap.method == "get"

    def test_an_unknown_selector_names_a_search(self) -> None:
        with pytest.raises(GaxiError) as caught:
            CATALOG.select("get:/absent/route")
        assert "no capability named" in caught.value.message
        assert caught.value.help_commands == ["gaxi capabilities route"]

    def test_a_selector_disambiguates_two_matching_templates(self) -> None:
        code, out, _ = run_cli(
            ["get", "/org/acme/widgets", "--as", "get:/org/{owner}/widgets"],
            responses=[json_response([])],
        )
        assert code == 0
        assert "count: 0" in out

    def test_a_selector_that_cannot_match_is_a_usage_failure(self) -> None:
        code, out, _ = run_cli(
            ["get", "/repos/acme/widgets/pulls", "--as", "post:/repos/{owner}/{repo}/issues"],
        )
        assert code == EXIT_USAGE
        assert "does not match GET /repos/acme/widgets/pulls" in out


class CapabilityDetailTest(unittest.TestCase):
    def test_an_unavailable_capability_reports_only_its_reason(self) -> None:
        code, out, _ = run_cli(["capability", "get:/admin/unsupported"])
        assert code == 0
        assert "  available: false" in out
        assert "  reason: " in out

    def test_a_destructive_capability_suggests_the_acknowledgement(self) -> None:
        code, out, _ = run_cli(["capability", "delete:/repos/{owner}/{repo}/issues/comments/{id}"])
        assert code == 0
        assert "--yes" in out

    def test_an_unknown_mutation_suggests_allow_unknown(self) -> None:
        code, out, _ = run_cli(["capability", "post:/repos/{owner}/{repo}/releases/{id}/assets"])
        assert code == 0
        assert "--allow-unknown" in out

    def test_paging_the_catalog_offers_the_next_page(self) -> None:
        code, out, _ = run_cli(["capabilities", "repos", "--limit", "1"])
        assert code == 0
        assert "capabilities repos --page 2" in out

    def test_capability_detail_lists_entity_fields_with_projection_flags(self) -> None:
        code, out, _ = run_cli(
            ["capability", "get:/repos/{owner}/{repo}/issues/{index}/comments"],
        )
        assert code == 0
        assert "entity_fields[" in out
        assert "id,integer,true" in out
        assert "user.login,string,true" in out
        assert "body,string,true" in out
        assert "created_at,string,true" in out
        assert "updated_at,string,false" in out
        assert "assets,array,false" in out

    def test_capability_detail_omits_entity_fields_without_an_entity_schema(self) -> None:
        code, out, _ = run_cli(["capability", "delete:/repos/{owner}/{repo}/issues/comments/{id}"])
        assert code == 0
        assert "entity_fields[" not in out

    def test_capability_detail_survives_cyclic_entity_schema_refs(self) -> None:
        document = {
            "swagger": "2.0",
            "basePath": "/api/v1",
            "paths": {
                "/repos/{owner}/{repo}": {
                    "get": {
                        "operationId": "repoGet",
                        "parameters": [
                            {"name": "owner", "in": "path", "type": "string", "required": True},
                            {"name": "repo", "in": "path", "type": "string", "required": True},
                        ],
                        "responses": {
                            "200": {
                                "description": "Repository",
                                "schema": {"$ref": "#/definitions/Repository"},
                            },
                        },
                    },
                },
            },
            "definitions": {
                "Repository": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "parent": {"$ref": "#/definitions/Repository"},
                    },
                },
            },
        }
        code, out, _ = run_cli(
            ["capability", "get:/repos/{owner}/{repo}"],
            document=document,
        )
        assert code == 0
        assert "entity_fields[" in out
        assert "name,string," in out
        assert "parent,object," in out


class SetupTest(unittest.TestCase):
    def test_setup_requires_a_known_action(self) -> None:
        code, out, _ = run_cli(["setup"])
        assert code == EXIT_USAGE
        assert "setup requires one of skill, hook" in out

    def test_unreadable_settings_are_a_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{ not json", encoding="utf-8")
            code, out, _ = run_cli(["setup", "hook", "--path", str(path)])
            assert code == 1
            assert "cannot read" in out


class ProjectionTest(unittest.TestCase):
    def test_list_indices_are_resolvable(self) -> None:
        assert resolve_path({"a": [{"b": 1}]}, "a.0.b") == 1

    def test_a_structured_value_is_flattened_to_json(self) -> None:
        assert cell_value({"a": 1}) == '{"a":1}'

    def test_a_field_observed_but_undeclared_is_accepted(self) -> None:
        validate_fields(["extra"], [{"extra": 1}])

    def test_a_nested_field_is_accepted_when_it_resolves(self) -> None:
        validate_fields(["a.b"], [{"a": {"b": 1}}], declared=["c"])


class ContextIdentityTest(unittest.TestCase):
    def test_a_repository_without_an_origin_remote_uses_the_first(self) -> None:
        repo = RepositoryContext(
            root="/repo",
            branch="main",
            remotes=[parse_remote("upstream", support.REMOTE)],
        )
        code, out, _ = run_cli(["context"], repo=repo)
        assert code == 0
        assert "  repository: acme/widgets" in out


class FlakyTransport:
    """Fails the first request, then replays a scripted response."""

    def __init__(self, reply: Response) -> None:
        self.reply = reply
        self.calls = 0

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        *,
        stream: bool = False,
    ) -> Response:
        del method, url, headers, body, stream
        self.calls += 1
        if self.calls == 1:
            msg = "cannot reach the instance"
            raise GaxiError(msg)
        return self.reply


class RetryTest(unittest.TestCase):
    def test_a_safe_request_retries_after_a_transport_failure(self) -> None:
        transport = FlakyTransport(json_response([]))
        session = support.make_session()
        session.transport = transport
        code, out, _ = run_cli(["get", "/repos/acme/widgets/pulls"], session=session)
        assert code == 0
        assert transport.calls == 2
        assert "count: 0" in out

    def test_an_unsafe_request_reports_the_transport_failure(self) -> None:
        transport = FlakyTransport(json_response({}))
        session = support.make_session()
        session.transport = transport
        code, out, _ = run_cli(
            ["post", "/repos/acme/widgets/issues", "title=x", "--allow-unknown"],
            session=session,
        )
        assert code == 1
        assert transport.calls == 1
        assert "cannot reach the instance" in out

    def test_an_unsafe_request_does_not_retry(self) -> None:
        code, out, _ = run_cli(
            ["post", "/repos/acme/widgets/issues", "title=x", "--allow-unknown"],
            responses=[response(503, b"", media_type="text/plain")],
        )
        assert code == 1
        assert "request failed with status 503" in out
