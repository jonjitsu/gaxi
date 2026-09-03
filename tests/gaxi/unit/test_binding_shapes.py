"""Binding rejections and the descriptions bindings produce."""

import unittest

import pytest

from gaxi.binding import Binding, bind, split_assignment
from gaxi.catalog import Catalog
from gaxi.errors import UsageError
from gaxi.jsonbody import validate_binding_body_required, validate_json_body
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)
LIST_PULLS = CATALOG.by_key["get:/repos/{owner}/{repo}/pulls"]
CREATE_ISSUE = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
ISSUE_DEPENDENCY = CATALOG.by_key["post:/repos/{owner}/{repo}/issues/{index}/dependencies"]


class AssignmentTest(unittest.TestCase):
    def test_an_argument_without_an_equals_sign_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            split_assignment("state")
        assert "expected an input assignment name=value" in caught.value.message

    def test_an_unknown_qualifier_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(CREATE_ISSUE, ["header:title=x"])
        assert "unknown input qualifier" in caught.value.message

    def test_a_qualified_name_the_capability_lacks_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(CREATE_ISSUE, ["body:absent=x"])
        assert "declares no body property named absent" in caught.value.message
        with pytest.raises(UsageError) as caught:
            bind(LIST_PULLS, ["query:absent=x"])
        assert "declares no query input named absent" in caught.value.message

    def test_a_boolean_input_only_accepts_true_or_false(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(CREATE_ISSUE, ["closed=maybe"])
        assert "expects true or false" in caught.value.message

    def test_booleans_are_rendered_as_words_in_a_query(self) -> None:
        binding = bind(CREATE_ISSUE, ["title=Ship", "closed=true"])
        assert binding.body == {"title": "Ship", "closed": True}


class DescriptionTest(unittest.TestCase):
    def test_a_binding_describes_every_location_it_fills(self) -> None:
        binding = Binding()
        binding.query.append(("state", "open"))
        binding.form.append(("name", "asset"))
        binding.files.append(("attachment", "/tmp/a.zip"))  # noqa: S108
        binding.body = {"title": "Ship"}
        assert binding.describe() == [
            ("query:state", "open"),
            ("form:name", "asset"),
            ("file:attachment", "/tmp/a.zip"),  # noqa: S108
            ("body", '{"title": "Ship"}'),
        ]

    def test_an_empty_binding_describes_nothing(self) -> None:
        assert Binding().describe() == []
        assert Binding().query_string() == ""


class JsonBodyTest(unittest.TestCase):
    def test_invalid_json_is_rejected_with_its_position(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_json_body(CREATE_ISSUE, "{ not json")
        assert "--input-json is not valid JSON" in caught.value.message
        assert caught.value.details[0][0] == "position"

    def test_a_non_object_body_is_rejected_when_properties_are_declared(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_json_body(CREATE_ISSUE, "1")
        assert "must be a JSON object" in caught.value.message

    def test_a_capability_without_a_body_schema_accepts_anything(self) -> None:
        assert validate_json_body(LIST_PULLS, "[1, 2]") == [1, 2]

    def test_declared_types_are_enforced(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_json_body(CREATE_ISSUE, '{"title": 1}')
        assert "title expects string" in caught.value.message

    def test_booleans_are_not_integers(self) -> None:
        with pytest.raises(UsageError) as caught:
            validate_json_body(CREATE_ISSUE, '{"title": "x", "labels": true}')
        assert "labels expects array" in caught.value.message

    def test_binding_body_required_skips_non_object_bodies(self) -> None:
        binding = Binding()
        binding.body = "literal"
        validate_binding_body_required(ISSUE_DEPENDENCY, binding)

    def test_binding_body_required_skips_non_object_batch_elements(self) -> None:
        binding = Binding()
        binding.batch_bodies = [{"index": 22, "owner": "acme"}, "skip-me"]
        validate_binding_body_required(ISSUE_DEPENDENCY, binding)

    def test_input_json_required_is_checked_after_path_defaults(self) -> None:
        binding = bind(
            ISSUE_DEPENDENCY,
            [],
            input_json='{"index": 22}',
            path_values={"owner": "trading", "repo": "lab3", "index": "23"},
        )
        assert binding.body == {"index": 22, "owner": "trading", "repo": "lab3"}
