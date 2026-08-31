"""The remaining edges: fallbacks, overlays, and entry points."""

import subprocess
import unittest
import unittest.mock
from typing import Any

import gaxi.__main__
from gaxi import jsonshape, repo_context
from gaxi.binding import _as_query_text
from gaxi.capability import Capability, Param
from gaxi.catalog import Catalog
from gaxi.config import Config
from gaxi.credentials import CredentialResolver
from gaxi.discovery import _remote_origin, _sole_remote_origin
from gaxi.document import Document
from gaxi.encode import _yaml_lines, to_yaml
from gaxi.jsonbody import _json_type_matches, body_properties
from gaxi.planner import Planner
from gaxi.policy import Policy
from gaxi.projection import validate_fields
from gaxi.repo_context import RepositoryContext, parse_remote
from gaxi.session import Options
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT
from tests.gaxi.support import json_response, run_cli

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)


class EntryPointTest(unittest.TestCase):
    def test_the_module_entry_point_exposes_main(self) -> None:
        assert gaxi.__main__ is not None

    def test_the_json_aliases_are_importable(self) -> None:
        assert jsonshape.JsonObject is not None


class QueryTextTest(unittest.TestCase):
    def test_booleans_are_rendered_as_words(self) -> None:
        assert _as_query_text(True) == "true"
        assert _as_query_text(False) == "false"
        assert _as_query_text(3) == "3"


class OriginFallbackTest(unittest.TestCase):
    def test_a_remote_with_neither_origin_nor_host_maps_to_nothing(self) -> None:
        assert _remote_origin(parse_remote("weird", "not a url"), Config({})) is None

    def test_two_different_remotes_are_ambiguous(self) -> None:
        repository = RepositoryContext(
            root="/repo",
            branch="main",
            remotes=[
                parse_remote("a", "https://one.example.com/acme/widgets.git"),
                parse_remote("b", "https://two.example.com/acme/widgets.git"),
            ],
        )
        assert _sole_remote_origin(Config({}), repository) is None


class GitTest(unittest.TestCase):
    def test_a_successful_command_is_stripped(self) -> None:
        completed: Any = subprocess.CompletedProcess(["git"], 0, "/repo\n", "")
        with unittest.mock.patch.object(subprocess, "run", return_value=completed):
            assert repo_context._git(["rev-parse"], ".") == "/repo"


class YamlScalarTest(unittest.TestCase):
    def test_a_bare_scalar_document_renders_as_one_line(self) -> None:
        assert _yaml_lines(3, 0) == ["3"]
        assert to_yaml(Document()) == ""


class JsonBodyEdgeTest(unittest.TestCase):
    def test_a_non_object_body_schema_declares_no_properties(self) -> None:
        cap = Capability(
            method="post",
            path="/x",
            body=Param(name="body", location="body", schema={"type": "array"}),
        )
        assert body_properties(cap) == {}

    def test_an_unknown_declared_type_is_accepted(self) -> None:
        assert _json_type_matches("null", None) is True

    def test_a_boolean_is_never_an_integer(self) -> None:
        assert _json_type_matches("integer", True) is False
        assert _json_type_matches("integer", 3) is True


class CredentialEdgeTest(unittest.TestCase):
    def test_a_helper_that_returns_nothing_supplies_no_credential(self) -> None:
        config = Config({"servers": {support.ORIGIN: {"credential_helper": ["helper"]}}})
        resolver = CredentialResolver(config, {})
        with unittest.mock.patch(
            "gaxi.credentials.run_helper", return_value="",
        ):
            assert resolver.resolve(support.ORIGIN) is None


class PlannerEdgeTest(unittest.TestCase):
    def planner(self, key: str, path: str, **query: str) -> Planner:
        cap = CATALOG.by_key[key]
        binding: Any = unittest.mock.Mock(query=list(query.items()), body=None)
        return Planner(CATALOG, cap, path, binding, Options())

    def test_a_top_level_path_has_no_parent_collection(self) -> None:
        assert self.planner("get:/user", "/user").parent_collection() is None

    def test_a_parent_the_catalog_does_not_advertise_is_not_suggested(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/archive/{archive}",
            "/repos/acme/widgets/archive/main.zip",
        )
        assert planner.parent_collection() is None

    def test_an_unparsable_page_stops_the_next_page_suggestion(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/pulls", "/repos/acme/widgets/pulls",
            page="one", limit="20",
        )
        assert planner.next_page(unittest.mock.Mock(payload=[], total=None)) is None

    def test_body_assignments_are_carried_into_a_retry(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
        binding: Any = unittest.mock.Mock(query=[], body={"title": "Ship", "labels": [1]})
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/issues", binding, Options())
        assert "body:title=Ship" in planner.retry()
        assert "labels" not in planner.retry()

    def test_related_suggestions_stop_at_the_limit(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues/{index}", "/repos/acme/widgets/issues/1",
        )
        assert len(planner.related_suggestions(limit=1)) <= 1


class OverlayTest(unittest.TestCase):
    def test_an_entity_overlay_cannot_displace_a_built_in_rule(self) -> None:
        overlay = {"entities": {"PullRequest": {"entity": "reviews"}}}
        props = Policy(user_overlay=overlay).resolve(
            CATALOG.by_key["get:/repos/{owner}/{repo}/pulls"],
        )
        assert props.entity == "pull_requests"
        assert props.sources["entity"] == "builtin"

    def test_a_repository_overlay_reaches_presentation_only(self) -> None:
        overlay = {"entities": {"PullRequest": {"confirmation": "none"}}}
        props = Policy(repo_overlay=overlay).resolve(
            CATALOG.by_key["get:/repos/{owner}/{repo}/pulls"],
        )
        assert props.confirmation == "none"
        assert props.sources["confirmation"] == "invariant"


class ProjectionEdgeTest(unittest.TestCase):
    def test_a_declared_field_is_accepted_without_being_observed(self) -> None:
        validate_fields(["index"], [], declared=["index"])

    def test_a_field_resolvable_in_one_item_is_accepted(self) -> None:
        validate_fields(["a.b"], [{"c": 1}, {"a": {"b": 2}}])


class DetailFallbackTest(unittest.TestCase):
    def test_a_body_schema_is_reported_in_capability_detail(self) -> None:
        code, out, _ = run_cli(["capability", "post:/repos/{owner}/{repo}/issues"])
        assert code == 0
        assert "title,body,true" in out or "title" in out

    def test_a_projected_field_the_response_omits_reads_as_null(self) -> None:
        code, out, _ = run_cli(
            ["get", "/repos/acme/widgets/pulls/41"],
            responses=[json_response({"unexpected": {"nested": 1}})],
        )
        assert code == 0
        assert out.startswith("pull_request:")
        assert "  index: null" in out
