"""The last contract edges: exhausted loops, absent metadata, and defaults."""

import json
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

from gaxi.binding import bind
from gaxi.capability import Capability, Param, ResponseSpec
from gaxi.catalog import Catalog
from gaxi.config import Config
from gaxi.discovery import load_catalog
from gaxi.jsonbody import validate_json_body
from gaxi.planner import Planner
from gaxi.projection import observed_fields, validate_fields
from gaxi.repo_context import RepositoryContext
from gaxi.transport import RecordingTransport, Response
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT
from tests.gaxi.support import json_response, response, run_cli

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)
BASE: dict[str, Any] = {"swagger": "2.0", "basePath": "/api/v1", "info": {"title": "t"}}


class BindingDefaultTest(unittest.TestCase):
    def test_pagination_defaults_can_be_declined(self) -> None:
        cap = CATALOG.by_key["get:/repos/{owner}/{repo}/pulls"]
        assert bind(cap, [], apply_pagination=False).query == []
        assert dict(bind(cap, []).query) == {"page": "1", "limit": "20"}


class ResponseSelectionTest(unittest.TestCase):
    def test_informational_statuses_are_skipped(self) -> None:
        cap = Capability(
            method="get",
            path="/x",
            responses={
                100: ResponseSpec(status=100, kind="empty"),
                200: ResponseSpec(status=200, kind="object"),
            },
        )
        spec = cap.success_response()
        assert spec is not None
        assert spec.status == 200

    def test_a_capability_with_only_failures_has_no_success_response(self) -> None:
        cap = Capability(
            method="get", path="/x", responses={404: ResponseSpec(status=404, kind="empty")},
        )
        assert cap.success_response() is None


class RedirectEdgeTest(unittest.TestCase):
    def test_a_redirect_without_a_location_is_reported_as_one(self) -> None:
        code, out, _ = run_cli(
            ["get", "/repos/acme/widgets/redirect"], responses=[response(302, b"")],
        )
        assert code == 0
        assert out.startswith("redirect:")
        assert "  status: 302" in out


class ProjectionEdgeTest(unittest.TestCase):
    def test_non_object_items_contribute_no_field_names(self) -> None:
        assert observed_fields([1, "two", {"a": 1}]) == ["a"]

    def test_an_indexable_path_is_accepted_without_a_declared_head(self) -> None:
        validate_fields(["0.x"], [[{"x": 1}]])

    def test_a_collection_of_scalars_falls_back_to_declared_names(self) -> None:
        code, out, _ = run_cli(
            ["get", "/repos/acme/widgets/pulls"], responses=[json_response([1, 2])],
        )
        assert code == 0
        assert "count: 2" in out

    def test_a_policy_projection_survives_a_response_with_no_fields(self) -> None:
        raw = {
            **BASE,
            "paths": {"/things": {"get": {
                "operationId": "listThings",
                "responses": {"200": {"description": "d", "schema": {"type": "array"}}},
            }}},
        }
        overlay = {"capabilities": {"get:/things": {"projection": ["name"]}}}
        session = support.make_session(
            document=raw, responses=[json_response([1, 2])],
        )
        session._policy = None
        session._config = Config({"overlays": {support.ORIGIN: overlay}})
        code, out, _ = run_cli(["get", "/things"], session=session)
        assert code == 0
        assert "{name}" in out


class JsonBodyEdgeTest(unittest.TestCase):
    def test_additional_properties_allow_undeclared_names(self) -> None:
        cap = Capability(
            method="post",
            path="/x",
            body=Param(
                name="body",
                location="body",
                schema={
                    "type": "object",
                    "additionalProperties": True,
                    "properties": {"title": {"type": "string"}},
                },
            ),
        )
        assert validate_json_body(cap, '{"title": "x", "extra": 1}') == {
            "title": "x", "extra": 1,
        }


class CatalogViewTest(unittest.TestCase):
    def test_a_catalog_with_nothing_unavailable_says_nothing(self) -> None:
        raw = {**BASE, "paths": {"/things": {"get": {"operationId": "listThings"}}}}
        code, out, _ = run_cli(["capabilities"], document=raw)
        assert code == 0
        assert "unavailable" not in out

    def test_a_search_that_matches_nothing_suggests_nothing_specific(self) -> None:
        code, out, _ = run_cli(["capabilities", "zzzz"])
        assert code == 0
        assert "count: 0" in out

    def test_a_narrow_search_offers_no_next_page(self) -> None:
        code, out, _ = run_cli(["capabilities", "redirect"])
        assert code == 0
        assert "--page 2" not in out

    def test_a_capability_without_an_operation_id_still_renders(self) -> None:
        raw = {**BASE, "paths": {"/things": {"get": {}}}}
        code, out, _ = run_cli(["capability", "get:/things"], document=raw)
        assert code == 0
        assert "  key: get:/things" in out
        assert "operation_id" not in out


class AuthListingTest(unittest.TestCase):
    def test_an_environment_credential_is_listed(self) -> None:
        code, out, _ = run_cli(
            ["auth", "list"],
            env={"GITEA_SERVER": support.ORIGIN, "GITEA_TOKEN": "secret"},
        )
        assert code == 0
        assert "environment" in out
        assert "secret" not in out


class PlannerEdgeTest(unittest.TestCase):
    def test_a_literal_child_route_is_not_a_detail_suggestion(self) -> None:
        cap = CATALOG.by_key["get:/repos/{owner}/{repo}/issues/{index}"]
        binding: Any = unittest.mock.Mock(query=[], body=None)
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/issues/1", binding)
        assert planner.detail_suggestion() is None

    def test_a_supplied_filter_value_is_not_suggested_again(self) -> None:
        cap = CATALOG.by_key["get:/repos/{owner}/{repo}/pulls"]
        binding: Any = unittest.mock.Mock(query=[("state", "open")], body=None)
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/pulls", binding)
        suggestion = planner.alternative_filter()
        assert suggestion is not None
        assert "state=closed" in suggestion


class SessionCacheTest(unittest.TestCase):
    def test_the_policy_is_resolved_once(self) -> None:
        session = support.make_session()
        assert session.policy is session.policy


class LastArcsTest(unittest.TestCase):
    def test_auth_list_without_environment_credentials(self) -> None:
        code, out, _ = run_cli(["auth", "list"], env={})
        assert code == 0
        assert "count: 0" in out

    def test_the_skill_is_generated_outside_a_repository(self) -> None:
        code, out, _ = run_cli(["skill"], repo=RepositoryContext())
        assert code == 0
        assert "## Capability vocabulary" not in out
        assert "## Discovery" in out

    def test_a_cache_validated_only_by_modification_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            document = Response(
                200,
                [("Content-Type", "application/json"), ("Last-Modified", "yesterday")],
                json.dumps(DOCUMENT).encode("utf-8"),
            )
            first = Response(
                200, [("Content-Type", "application/json")],
                json.dumps(DOCUMENT).encode("utf-8"),
            )
            load_catalog(support.ORIGIN, RecordingTransport([first, document]), cache)
            with unittest.mock.patch.object(time, "time", return_value=time.time() + 10_000):
                revalidating = RecordingTransport([Response(304, [])])
                load_catalog(support.ORIGIN, revalidating, cache)
            sent = revalidating.requests[0]["headers"]
            assert sent == {"If-Modified-Since": "yesterday"}

    def test_a_single_valued_filter_offers_no_alternative(self) -> None:
        raw = {
            **BASE,
            "paths": {"/things": {"get": {
                "operationId": "listThings",
                "parameters": [
                    {"name": "state", "in": "query", "type": "string", "enum": ["open"]},
                ],
            }}},
        }
        catalog = Catalog.from_document(raw, origin=support.ORIGIN)
        cap = catalog.by_key["get:/things"]
        binding: Any = unittest.mock.Mock(query=[("state", "open")], body=None)
        planner = Planner(catalog, cap, "/things", binding)
        assert planner.alternative_filter() is None

    def test_a_dry_run_of_a_capability_without_an_operation_id(self) -> None:
        raw = {**BASE, "paths": {"/things": {"get": {}}}}
        code, out, _ = run_cli(["get", "/things", "--dry-run"], document=raw)
        assert code == 0
        assert "operation_id" not in out

    def test_an_overlay_projection_the_response_lacks_falls_back(self) -> None:
        raw = {
            **BASE,
            "paths": {"/things": {"get": {
                "operationId": "listThings",
                "responses": {"200": {"description": "d", "schema": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"name": {"type": "string"}}},
                }}},
            }}},
        }
        overlay = {"capabilities": {"get:/things": {"projection": ["absent"]}}}
        session = support.make_session(document=raw, responses=[json_response([1, 2])])
        session._config = Config({"overlays": {support.ORIGIN: overlay}})
        session._policy = None
        code, out, _ = run_cli(["get", "/things"], session=session)
        assert code == 0
        assert "{name}" in out
