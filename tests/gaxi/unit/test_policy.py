import unittest
from typing import override

from gaxi.catalog import Catalog
from gaxi.policy import Policy, Properties, fallback_projection
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
