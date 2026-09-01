"""The remaining edges: fallbacks, overlays, and entry points."""

import copy
import re
import subprocess
import unittest
import unittest.mock
from typing import Any

import pytest

import gaxi.__main__
from gaxi import jsonshape, repo_context
from gaxi.binding import _as_query_text, bind
from gaxi.capability import Capability, Param
from gaxi.catalog import Catalog
from gaxi.classify import Classification
from gaxi.config import Config
from gaxi.credentials import CredentialResolver
from gaxi.discovery import _remote_origin, _sole_remote_origin
from gaxi.document import Document
from gaxi.encode import _yaml_lines, to_yaml
from gaxi.errors import UsageError
from gaxi.jsonbody import _json_type_matches, body_properties
from gaxi.options import Options, RequestOptions
from gaxi.planner import (
    Planner,
    _identifier_from_payload,
    _is_usable_identifier,
    _placeholder_compatible,
)
from gaxi.policy import Policy
from gaxi.projection import validate_fields
from gaxi.repo_context import RepositoryContext, parse_remote
from gaxi.suggestions import build
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT
from tests.gaxi.support import json_response, run_cli

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)
CREATE_ISSUE = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]


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
        return Planner(CATALOG, cap, path, binding)

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
        binding: Any = unittest.mock.Mock(
            query=[],
            body={"title": "Ship", "labels": [1]},
            batch_bodies=None,
        )
        binding.is_batch.return_value = False
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/issues", binding)
        assert "body:title=Ship" in planner.retry()
        assert "labels" not in planner.retry()

    def test_batch_input_json_is_carried_into_a_retry(self) -> None:
        payload = '[{"title": "a"}, {"title": "b"}]'
        binding = bind(CREATE_ISSUE, [], input_json=payload)
        session = support.make_session(
            options=Options(request=RequestOptions(input_json=payload)),
        )
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            binding,
            session,
        )
        assert (
            planner.retry(["--yes"])
            == "gaxi post /repos/acme/widgets/issues "
            "--input-json '[{\"title\": \"a\"}, {\"title\": \"b\"}]' --yes"
        )
        assert (
            planner.retry(["--allow-unknown"])
            == "gaxi post /repos/acme/widgets/issues "
            "--input-json '[{\"title\": \"a\"}, {\"title\": \"b\"}]' --allow-unknown"
        )

    def test_batch_input_json_serialises_bodies_without_a_session(self) -> None:
        binding = bind(CREATE_ISSUE, [], input_json='[{"title": "a"}]')
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            binding,
        )
        assert (
            planner.retry()
            == 'gaxi post /repos/acme/widgets/issues --input-json \'[{"title":"a"}]\''
        )

    def test_batch_input_json_falls_back_when_the_session_has_no_payload(self) -> None:
        binding = bind(CREATE_ISSUE, [], input_json='[{"title": "a"}]')
        session = support.make_session(options=Options(request=RequestOptions()))
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            binding,
            session,
        )
        assert (
            planner.retry()
            == 'gaxi post /repos/acme/widgets/issues --input-json \'[{"title":"a"}]\''
        )

    def test_shell_metacharacters_in_batch_json_are_single_quoted(self) -> None:
        payload = '[{"title": "$(printf INJECTED)"}]'
        binding = bind(CREATE_ISSUE, [], input_json=payload)
        session = support.make_session(
            options=Options(request=RequestOptions(input_json=payload, input_json_source=payload)),
        )
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            binding,
            session,
        )
        assert (
            planner.retry(["--yes"])
            == "gaxi post /repos/acme/widgets/issues "
            "--input-json '[{\"title\": \"$(printf INJECTED)\"}]' --yes"
        )

    def test_batch_input_json_from_a_file_keeps_the_source_reference(self) -> None:
        binding = bind(CREATE_ISSUE, [], input_json='[{"title": "a"}]')
        session = support.make_session(
            options=Options(
                request=RequestOptions(
                    input_json='[{"title": "a"}]',
                    input_json_source="@/tmp/bodies.jsonl",
                ),
            ),
        )
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            binding,
            session,
        )
        assert (
            planner.retry(["--yes"])
            == "gaxi post /repos/acme/widgets/issues --input-json @/tmp/bodies.jsonl --yes"
        )

    def test_related_suggestions_are_collected_for_rendering(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues/{index}", "/repos/acme/widgets/issues/1",
        )
        assert build(*planner.related_suggestions())

    def test_a_mutation_detail_suggests_the_created_entity(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
        binding: Any = unittest.mock.Mock(query=[], body={"title": "Ship"})
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/issues", binding)
        classification = Classification(
            "object", payload={"id": 277, "number": 7, "title": "Ship"},
        )
        suggestions = planner.for_detail(classification, effect="mutate")
        assert suggestions[0] == "gaxi get /repos/acme/widgets/issues/7"
        assert suggestions[1] == "gaxi get /repos/acme/widgets/issues/7/comments"

    def test_detail_fields_full_builds_a_read_command(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
        binding: Any = unittest.mock.Mock(query=[], body={"title": "Ship"})
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/issues", binding)
        assert planner.detail_fields_full({"number": 7}, ["title"]) == (
            "gaxi get /repos/acme/widgets/issues/7 --fields title --full"
        )

    def test_detail_fields_full_returns_none_without_an_identifier(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
        binding: Any = unittest.mock.Mock(query=[], body={"title": "Ship"})
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/issues", binding)
        assert planner.detail_fields_full({}, ["title"]) is None

    def test_detail_suggestion_uses_the_projected_identifier_placeholder(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues", "/repos/acme/widgets/issues",
        )
        suggestion = planner.detail_suggestion(["number", "title", "state", "updated_at"])
        assert suggestion == "gaxi get /repos/acme/widgets/issues/<number>"

    def test_detail_suggestion_falls_back_to_the_path_parameter(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues", "/repos/acme/widgets/issues",
        )
        assert planner.detail_suggestion() == "gaxi get /repos/acme/widgets/issues/<index>"
        assert planner.detail_suggestion(["title", "state"]) == (
            "gaxi get /repos/acme/widgets/issues/<index>"
        )

    def test_detail_suggestion_uses_policy_projection_when_fields_omit_it(self) -> None:
        session = support.make_session()
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues", "/repos/acme/widgets/issues",
        )
        planner.session = session
        assert planner.detail_suggestion() == "gaxi get /repos/acme/widgets/issues/<number>"
        assert planner.detail_suggestion(["title", "state"], allow_policy_fallback=False) == (
            "gaxi get /repos/acme/widgets/issues/<index>"
        )

    def test_detail_suggestion_rejects_an_incompatible_projected_identifier(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues", "/repos/acme/widgets/issues",
        )
        assert planner.detail_suggestion(["id", "title", "state"]) == (
            "gaxi get /repos/acme/widgets/issues/<index>"
        )

    def test_detail_suggestion_keeps_a_name_keyed_path_parameter(self) -> None:
        raw: dict[str, Any] = copy.deepcopy(DOCUMENT)
        raw["definitions"]["Tag"] = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
            },
        }
        raw["paths"]["/repos/{owner}/{repo}/tags"] = {
            "get": {
                "operationId": "repoListTags",
                "parameters": raw["paths"]["/repos/{owner}/{repo}/pulls"]["get"]["parameters"][:2],
                "responses": {
                    "200": {
                        "description": "TagList",
                        "schema": {"type": "array", "items": {"$ref": "#/definitions/Tag"}},
                    },
                },
            },
        }
        raw["paths"]["/repos/{owner}/{repo}/tags/{tag}"] = {
            "get": {
                "operationId": "repoGetTag",
                "parameters": [
                    *raw["paths"]["/repos/{owner}/{repo}/pulls"]["get"]["parameters"][:2],
                    {"name": "tag", "in": "path", "type": "string", "required": True},
                ],
                "responses": {
                    "200": {"description": "Tag", "schema": {"$ref": "#/definitions/Tag"}},
                },
            },
        }
        catalog = Catalog.from_document(raw, origin=support.ORIGIN)
        cap = catalog.by_key["get:/repos/{owner}/{repo}/tags"]
        binding: Any = unittest.mock.Mock(query=[], body=None)
        planner = Planner(catalog, cap, "/repos/acme/widgets/tags", binding)
        assert planner.detail_suggestion(["id", "name"]) == (
            "gaxi get /repos/acme/widgets/tags/<tag>"
        )

    def test_detail_suggestions_use_only_compatible_placeholders(self) -> None:
        raw: dict[str, Any] = copy.deepcopy(DOCUMENT)
        raw["definitions"]["Tag"] = {
            "type": "object",
            "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
        }
        raw["paths"]["/repos/{owner}/{repo}/tags"] = {
            "get": {
                "operationId": "repoListTags",
                "parameters": raw["paths"]["/repos/{owner}/{repo}/pulls"]["get"]["parameters"][:2],
                "responses": {
                    "200": {
                        "description": "TagList",
                        "schema": {"type": "array", "items": {"$ref": "#/definitions/Tag"}},
                    },
                },
            },
        }
        raw["paths"]["/repos/{owner}/{repo}/tags/{tag}"] = {
            "get": {
                "operationId": "repoGetTag",
                "parameters": [
                    *raw["paths"]["/repos/{owner}/{repo}/pulls"]["get"]["parameters"][:2],
                    {"name": "tag", "in": "path", "type": "string", "required": True},
                ],
                "responses": {
                    "200": {"description": "Tag", "schema": {"$ref": "#/definitions/Tag"}},
                },
            },
        }
        catalog = Catalog.from_document(raw, origin=support.ORIGIN)
        session = support.make_session()
        for cap in catalog.available():
            if cap.method != "get":
                continue
            props = session.policy.resolve(cap)
            if props.response != "collection":
                continue
            binding: Any = unittest.mock.Mock(query=[], body=None)
            concrete_path = re.sub(r"\{[^{}]+\}", "acme", cap.path)
            planner = Planner(catalog, cap, concrete_path, binding)
            planner.session = session
            for _child_cap, rest in planner._child_of(cap.path):
                match = re.fullmatch(r"\{([^{}]+)\}", rest[0])
                if not match:
                    continue
                path_param = match.group(1)
                suggestion = planner.detail_suggestion()
                assert suggestion is not None
                placeholder = suggestion.rsplit("<", 1)[-1][:-1]
                assert _placeholder_compatible(path_param, placeholder), (
                    f"{cap.key} suggested <{placeholder}> for {{{path_param}}}"
                )
                break

    def test_detail_suggestion_keeps_the_path_parameter_without_a_declared_identifier(
        self,
    ) -> None:
        session = support.make_session()
        props = Policy().resolve(CATALOG.by_key["get:/repos/{owner}/{repo}/issues"])
        props.projection = ["title", "state"]
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues", "/repos/acme/widgets/issues",
        )
        planner.session = session
        with unittest.mock.patch.object(session.policy, "resolve", return_value=props):
            assert planner.detail_suggestion(["title", "state"]) == (
                "gaxi get /repos/acme/widgets/issues/<index>"
            )

    def test_a_mutation_without_an_identifier_falls_back_to_collection_siblings(self) -> None:
        raw: dict[str, Any] = copy.deepcopy(DOCUMENT)
        issue_list = raw["paths"]["/repos/{owner}/{repo}/issues"]["get"]
        raw["paths"]["/repos/{owner}/{repo}/issues/comments"] = {
            "get": {
                "operationId": "issueListRepoComments",
                "parameters": issue_list["parameters"],
                "responses": {"200": {"description": "CommentList", "schema": {"type": "array"}}},
            },
        }
        raw["paths"]["/repos/{owner}/{repo}/issues/pinned"] = {
            "get": {
                "operationId": "issueListPinned",
                "parameters": issue_list["parameters"],
                "responses": {"200": {"description": "IssueList", "schema": {"type": "array"}}},
            },
        }
        catalog = Catalog.from_document(raw, origin=support.ORIGIN)
        cap = catalog.by_key["post:/repos/{owner}/{repo}/issues"]
        binding: Any = unittest.mock.Mock(query=[], body={"title": "Ship"})
        planner = Planner(catalog, cap, "/repos/acme/widgets/issues", binding)
        classification = Classification("object", payload={"title": "Ship"})
        suggestions = planner.for_detail(classification, effect="mutate")
        assert suggestions == [
            "gaxi get /repos/acme/widgets/issues/comments",
            "gaxi get /repos/acme/widgets/issues/pinned",
        ]

    def test_a_read_detail_still_suggests_sub_resources(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues/{index}", "/repos/acme/widgets/issues/1",
        )
        suggestions = planner.for_detail(Classification("object", payload={"number": 1}),
                                         effect="read")
        assert suggestions[0] == "gaxi get /repos/acme/widgets/issues/1/comments"

    def test_an_empty_string_identifier_is_skipped(self) -> None:
        assert not _is_usable_identifier("")
        assert _is_usable_identifier(0)
        assert _identifier_from_payload({"index": "", "number": 3}, "index") == 3

    def test_identifier_skips_duplicate_candidate_names(self) -> None:
        assert _identifier_from_payload({"number": 5}, "index") == 5

    def test_identifier_prefers_number_over_id_for_index_routes(self) -> None:
        assert _identifier_from_payload({"id": 277, "number": 11}, "index") == 11

    def test_identifier_still_uses_id_for_id_keyed_routes(self) -> None:
        assert _identifier_from_payload({"id": 5, "number": 11}, "id") == 5

    def test_for_detail_without_a_classification_uses_related_suggestions(self) -> None:
        planner = self.planner(
            "get:/repos/{owner}/{repo}/issues/{index}", "/repos/acme/widgets/issues/1",
        )
        assert planner.for_detail()[0] == "gaxi get /repos/acme/widgets/issues/1/comments"

    def test_forbidden_with_a_credential_suggests_identity_lookup(self) -> None:
        session = support.make_session(
            env={"GITEA_SERVER": support.ORIGIN, "GITEA_TOKEN": "secret"},
        )
        planner = self.planner("post:/repos/{owner}/{repo}/issues", "/repos/acme/widgets/issues")
        planner.session = session
        assert planner.for_error(403) == ["gaxi get /user --fields login"]

    def test_forbidden_without_a_credential_suggests_auth_setup(self) -> None:
        planner = self.planner("post:/repos/{owner}/{repo}/issues", "/repos/acme/widgets/issues")
        assert planner.for_error(403) == ["gaxi auth add https://gitea.example.com"]

    def test_unauthorized_suggests_auth_setup(self) -> None:
        planner = self.planner("get:/user", "/user")
        assert planner.for_error(401) == ["gaxi auth add https://gitea.example.com"]

    def test_a_mutate_with_a_non_object_payload_falls_back(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
        binding: Any = unittest.mock.Mock(query=[], body={"title": "Ship"})
        planner = Planner(CATALOG, cap, "/repos/acme/widgets/issues", binding)
        suggestions = planner.for_detail(Classification("object", payload=None), effect="mutate")
        assert suggestions == []


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
    ISSUE_FIELDS = (
        "assets", "assignee", "assignees", "body", "closed_at", "comments",
        "content_version", "created_at", "due_date", "html_url", "id", "is_locked",
        "number", "title", "state", "updated_at",
    )

    def test_a_declared_field_is_accepted_without_being_observed(self) -> None:
        validate_fields(["index"], [], declared=["index"])

    def test_a_field_resolvable_in_one_item_is_accepted(self) -> None:
        validate_fields(["a.b"], [{"c": 1}, {"a": {"b": 2}}])

    def test_a_synonym_near_miss_is_suggested_and_ranked_first(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_fields(["index"], [], declared=self.ISSUE_FIELDS)
        details = dict(caught.value.details)
        assert details["did_you_mean"] == "number"
        assert details["known"].startswith("number,")

    def test_a_typo_near_miss_is_suggested(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_fields(["titl"], [], declared=["number", "title", "state"])
        details = dict(caught.value.details)
        assert details["did_you_mean"] == "title"
        assert details["known"].startswith("title,")

    def test_an_ambiguous_near_miss_omits_did_you_mean(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_fields(["nope"], [], declared=["name", "note", "node"])
        details = dict(caught.value.details)
        assert "did_you_mean" not in details

    def test_a_single_clear_typo_is_suggested(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_fields(["titl"], [], declared=["title"])
        details = dict(caught.value.details)
        assert details["did_you_mean"] == "title"

    def test_an_unknown_field_with_no_known_names_omits_did_you_mean(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_fields(["nope"], [], declared=[])
        details = dict(caught.value.details)
        assert details["known"] == "none observed"
        assert "did_you_mean" not in details

    def test_login_on_issue_fields_does_not_suggest_assignee(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_fields(["login"], [], declared=self.ISSUE_FIELDS)
        details = dict(caught.value.details)
        assert "did_you_mean" not in details


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
        assert "  number: null" in out
