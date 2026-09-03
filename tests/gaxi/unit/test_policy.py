import unittest
from typing import override

from gaxi.capability import ResponseSpec
from gaxi.catalog import Catalog
from gaxi.policy import (
    Policy,
    Properties,
    _entity_field_paths,
    _expand_entity_field,
    entity_field_rows,
    fallback_projection,
)
from gaxi.swagger import Description
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT, document_with_labels

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)


class PolicyTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.policy = Policy()

    def resolve(self, key: str) -> Properties:
        return self.policy.resolve(CATALOG.by_key[key])

    def test_properties_are_independent(self) -> None:
        props = self.resolve("get:/repos/{owner}/{repo}/pulls")
        assert (props.effect, props.confirmation, props.retry) == ("read", "none", "safe")

    def test_known_destructive_mutation_requires_confirmation(self) -> None:
        props = self.resolve("delete:/repos/{owner}/{repo}/issues/comments/{id}")
        assert props.effect == "mutate"
        assert props.confirmation == "required"
        assert props.sources["confirmation"] == "invariant"

    def test_known_ordinary_mutation_needs_no_acknowledgement(self) -> None:
        props = self.resolve("post:/repos/{owner}/{repo}/issues")
        assert props.confirmation == "none"
        assert props.sources["confirmation"] == "builtin"
        assert props.retry == "unsafe"

    def test_issue_dependency_is_a_known_ordinary_mutation(self) -> None:
        props = self.resolve("post:/repos/{owner}/{repo}/issues/{index}/dependencies")
        assert props.confirmation == "none"
        assert props.sources["confirmation"] == "builtin"
        assert props.retry == "unsafe"

    def test_unknown_mutation_semantics_are_named(self) -> None:
        props = self.resolve("post:/repos/{owner}/{repo}/releases/{id}/assets")
        assert props.confirmation == "unknown"
        assert props.sources["confirmation"] == "fallback"

    def test_policy_projection_is_source_faithful(self) -> None:
        props = self.resolve("get:/repos/{owner}/{repo}/pulls")
        assert props.entity == "pull_requests"
        assert props.projection == ["number", "title", "state", "merged"]

    def test_comment_projection_includes_body(self) -> None:
        props = self.resolve("get:/repos/{owner}/{repo}/issues/{index}/comments")
        assert props.entity == "comments"
        assert props.projection == ["id", "user.login", "body", "created_at"]

    def test_entity_field_rows_mark_the_default_projection(self) -> None:
        cap = CATALOG.by_key["get:/repos/{owner}/{repo}/issues/{index}/comments"]
        props = self.resolve(cap.key)
        rows = entity_field_rows(CATALOG.description, cap.success_response(), props.projection)
        assert rows == [
            ["id", "integer", True],
            ["body", "string", True],
            ["user.login", "string", True],
            ["user.full_name", "string", False],
            ["user.is_admin", "boolean", False],
            ["created_at", "string", True],
            ["updated_at", "string", False],
            ["assets", "array", False],
        ]

    def test_entity_field_rows_follow_inline_array_items_without_entity_ref(self) -> None:
        description = Description({
            "swagger": "2.0",
            "definitions": {
                "Gadget": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
        })
        spec = ResponseSpec(
            status=200,
            kind="collection",
            schema={"type": "array", "items": {"$ref": "#/definitions/Gadget"}},
        )
        assert entity_field_rows(description, spec, ["name"]) == [["name", "string", True]]

    def test_entity_field_rows_handle_unusual_property_shapes(self) -> None:
        description = Description({
            "swagger": "2.0",
            "definitions": {
                "Weird": {
                    "type": "object",
                    "properties": {
                        "bad": "not-a-schema",
                        "empty": {"type": "object"},
                        "opaque": {"type": "file"},
                    },
                },
            },
        })
        spec = ResponseSpec(
            status=200,
            kind="object",
            schema={"$ref": "#/definitions/Weird"},
            entity_ref="Weird",
        )
        assert entity_field_rows(description, spec, []) == [
            ["bad", "unknown", False],
            ["empty", "object", False],
            ["opaque", "file", False],
        ]

    def test_entity_field_paths_ignore_non_object_nodes(self) -> None:
        description = Description({"swagger": "2.0"})
        assert _entity_field_paths(description, "not-an-object", seen=set()) == []

    def test_entity_field_rows_stop_on_cyclic_schema_refs(self) -> None:
        description = Description({
            "swagger": "2.0",
            "definitions": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "child": {"$ref": "#/definitions/Node"},
                    },
                },
            },
        })
        spec = ResponseSpec(
            status=200,
            kind="object",
            schema={"$ref": "#/definitions/Node"},
            entity_ref="Node",
        )
        assert entity_field_rows(description, spec, ["name"]) == [
            ["name", "string", True],
            ["child", "object", False],
        ]

    def test_expand_entity_field_stops_when_ref_is_on_the_current_path(self) -> None:
        description = Description({
            "swagger": "2.0",
            "definitions": {
                "Node": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                },
            },
        })
        seen = {"Node"}
        assert _expand_entity_field(
            description,
            {"$ref": "#/definitions/Node"},
            "wrapper",
            seen,
        ) == [("wrapper", "object")]
        assert _expand_entity_field(
            description,
            {"$ref": "#/definitions/Node"},
            "",
            seen,
        ) == []

    def test_entity_field_rows_expand_sibling_refs_to_the_same_definition(self) -> None:
        description = Description({
            "swagger": "2.0",
            "definitions": {
                "User": {
                    "type": "object",
                    "properties": {
                        "login": {"type": "string"},
                        "full_name": {"type": "string"},
                    },
                },
                "PullReviewComment": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "path": {"type": "string"},
                        "resolver": {"$ref": "#/definitions/User"},
                        "user": {"$ref": "#/definitions/User"},
                    },
                },
                "Issue": {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer"},
                        "assignee": {"$ref": "#/definitions/User"},
                        "user": {"$ref": "#/definitions/User"},
                    },
                },
            },
        })
        comment_spec = ResponseSpec(
            status=200,
            kind="object",
            schema={"$ref": "#/definitions/PullReviewComment"},
            entity_ref="PullReviewComment",
        )
        comment_rows = entity_field_rows(
            description,
            comment_spec,
            ["id", "path", "user.login"],
        )
        assert ["user.login", "string", True] in comment_rows
        assert ["resolver.login", "string", False] in comment_rows

        issue_spec = ResponseSpec(
            status=200,
            kind="object",
            schema={"$ref": "#/definitions/Issue"},
            entity_ref="Issue",
        )
        issue_rows = entity_field_rows(description, issue_spec, ["user.login"])
        assert ["user.login", "string", True] in issue_rows
        assert ["assignee.login", "string", False] in issue_rows

    def test_entity_field_rows_ignore_non_object_success_schemas(self) -> None:
        description = Description({"swagger": "2.0"})
        spec = ResponseSpec(status=200, kind="text", schema={"type": "string"})
        assert entity_field_rows(description, spec, []) == []

    def test_label_projection_includes_exclusive(self) -> None:
        catalog = Catalog.from_document(document_with_labels(), origin=support.ORIGIN)
        props = Policy().resolve(catalog.by_key["get:/repos/{owner}/{repo}/labels"])
        assert props.entity == "labels"
        assert props.projection == ["id", "name", "color", "exclusive"]

    def test_fallback_entity_and_projection_for_unknown_schema(self) -> None:
        props = self.resolve("get:/org/{org}/widgets")
        assert props.entity == "widgets"
        assert props.projection == ["id", "name", "status", "colour"]
        assert props.sources["projection"] == "fallback"

    def test_fallback_projection_ordering(self) -> None:
        names = ["created_at", "body", "state", "title", "id", "html_url", "colour"]
        assert fallback_projection(names) == ["id", "title", "state", "colour"]

    def test_user_overlay_fills_unresolved_properties(self) -> None:
        overlay = {"capabilities": {"get:/org/{org}/widgets": {
            "entity": "gadgets", "projection": ["name", "status"]}}}
        props = Policy(user_overlay=overlay).resolve(
            CATALOG.by_key["get:/org/{org}/widgets"])
        assert props.entity == "gadgets"
        assert props.sources["entity"] == "user-overlay"

    def test_repository_overlay_cannot_weaken_confirmation(self) -> None:
        overlay = {"capabilities": {
            "delete:/repos/{owner}/{repo}/issues/comments/{id}": {"confirmation": "none"}}}
        props = Policy(repo_overlay=overlay).resolve(
            CATALOG.by_key["delete:/repos/{owner}/{repo}/issues/comments/{id}"])
        assert props.confirmation == "required"

    def test_policy_cannot_invent_a_capability(self) -> None:
        overlay = {"capabilities": {"get:/not/advertised": {"entity": "ghosts"}}}
        policy = Policy(user_overlay=overlay)
        assert CATALOG.by_key.get("get:/not/advertised") is None
        props = policy.resolve(CATALOG.by_key["get:/user"])
        assert props.entity_singular == "user"


if __name__ == "__main__":
    unittest.main()
