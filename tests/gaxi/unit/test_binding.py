import tempfile
import unittest
from pathlib import Path

import pytest

from gaxi.binding import bind
from gaxi.capability import Capability
from gaxi.catalog import Catalog
from gaxi.errors import UsageError
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)
PULLS = CATALOG.by_key["get:/repos/{owner}/{repo}/pulls"]
CREATE_ISSUE = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
UPLOAD = CATALOG.by_key["post:/repos/{owner}/{repo}/releases/{id}/assets"]


class BindingTest(unittest.TestCase):
    def test_query_assignment(self) -> None:
        binding = bind(PULLS, ["state=open"])
        assert ("state", "open") in binding.query

    def test_pagination_defaults_are_bounded_and_explicit(self) -> None:
        binding = bind(PULLS, [])
        assert dict(binding.query) == {"page": "1", "limit": "20"}
        assert binding.defaults == [("page", 1), ("limit", 20)]

    def test_caller_values_override_defaults(self) -> None:
        binding = bind(PULLS, ["page=2", "limit=5"])
        assert dict(binding.query) == {"page": "2", "limit": "5"}
        assert binding.defaults == []

    def test_repeated_assignments_bind_arrays_in_caller_order(self) -> None:
        binding = bind(PULLS, ["labels=3", "labels=7"])
        assert [value for name, value in binding.query if name == "labels"] == ["3", "7"]

    def test_duplicate_scalar_is_rejected(self) -> None:
        with pytest.raises(UsageError):
            bind(PULLS, ["state=open", "state=closed"])

    def test_invalid_enum_is_rejected_before_a_request(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(PULLS, ["state=sideways"])
        assert caught.value.exit_code == 2

    def test_invalid_type_is_rejected(self) -> None:
        with pytest.raises(UsageError):
            bind(PULLS, ["limit=many"])

    def test_unknown_input_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(PULLS, ["nonsense=1"])
        assert "declares no input" in caught.value.message

    def test_body_properties_bind_by_name(self) -> None:
        binding = bind(CREATE_ISSUE, ["title=Broken deployment", "closed=false"])
        assert binding.body == {"title": "Broken deployment", "closed": False}

    def test_body_array_property_repeats(self) -> None:
        binding = bind(CREATE_ISSUE, ["title=x", "labels=3", "labels=7"])
        assert binding.body["labels"] == [3, 7]

    def test_missing_required_body_property(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(CREATE_ISSUE, ["body=no title"])
        assert "missing required input body:title" in caught.value.message

    def test_ambiguous_name_requires_a_qualifier(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(_ambiguous(), ["name=x"])
        assert "declared in 2 locations" in caught.value.message

    def test_qualified_assignment_selects_a_location(self) -> None:
        binding = bind(_ambiguous(), ["query:name=x"])
        assert binding.query == [("name", "x")]
        binding = bind(_ambiguous(), ["body:name=x"])
        assert binding.body == {"name": "x"}

    def test_query_string_in_the_path_is_decoded(self) -> None:
        binding = bind(PULLS, [], path_query="state=closed")
        assert ("state", "closed") in binding.query

    def test_query_string_and_assignment_conflict(self) -> None:
        with pytest.raises(UsageError):
            bind(PULLS, ["state=open"], path_query="state=closed")

    def test_input_json_supplies_the_whole_body(self) -> None:
        binding = bind(CREATE_ISSUE, [], input_json='{"title": "x", "labels": [1]}')
        assert binding.body == {"title": "x", "labels": [1]}

    def test_input_json_rejects_unknown_properties(self) -> None:
        with pytest.raises(UsageError):
            bind(CREATE_ISSUE, [], input_json='{"title": "x", "nope": 1}')

    def test_input_json_rejects_wrong_types(self) -> None:
        with pytest.raises(UsageError):
            bind(CREATE_ISSUE, [], input_json='{"title": 7}')

    def test_input_json_excludes_body_assignments(self) -> None:
        with pytest.raises(UsageError):
            bind(CREATE_ISSUE, ["title=x"], input_json='{"title": "y"}')

    def test_file_input_requires_the_at_prefix_and_an_existing_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".zip") as handle:
            binding = bind(UPLOAD, [f"attachment=@{handle.name}"])
            assert binding.files == [("attachment", handle.name)]
        with pytest.raises(UsageError):
            bind(UPLOAD, ["attachment=plain-value"])
        with pytest.raises(UsageError):
            bind(UPLOAD, ["attachment=@" + str(Path(tempfile.gettempdir()) / "absent")])

    def test_at_prefix_is_literal_for_string_inputs(self) -> None:
        binding = bind(CREATE_ISSUE, ["title=@notafile"])
        assert binding.body == {"title": "@notafile"}

    def test_missing_required_form_input(self) -> None:
        with pytest.raises(UsageError) as caught:
            bind(UPLOAD, ["name=asset.zip"])
        assert "form:attachment" in caught.value.message

    def test_unbound_body_properties_default_from_path_values(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues/{index}/dependencies"]
        binding = bind(
            cap,
            ["index=22"],
            path_values={"owner": "trading", "repo": "lab3", "index": "23"},
        )
        assert binding.body == {"index": 22, "owner": "trading", "repo": "lab3"}

    def test_path_defaults_do_not_override_supplied_body_values(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues/{index}/dependencies"]
        binding = bind(
            cap,
            ["body:owner=other", "index=22"],
            path_values={"owner": "trading", "repo": "lab3", "index": "23"},
        )
        assert binding.body == {"owner": "other", "index": 22, "repo": "lab3"}

    def test_identifier_body_properties_are_not_defaulted_from_path(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues/{index}/dependencies"]
        with pytest.raises(UsageError) as caught:
            bind(
                cap,
                [],
                path_values={"owner": "trading", "repo": "lab3", "index": "23"},
            )
        assert "body:index" in caught.value.message

    def test_path_defaults_apply_to_input_json_bodies(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues/{index}/dependencies"]
        binding = bind(
            cap,
            [],
            input_json='{"index": 22}',
            path_values={"owner": "trading", "repo": "lab3", "index": "23"},
        )
        assert binding.body == {"index": 22, "owner": "trading", "repo": "lab3"}

    def test_path_defaults_apply_to_batch_input_json_bodies(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues/{index}/dependencies"]
        binding = bind(
            cap,
            [],
            input_json='[{"index": 22}, {"index": 21}]',
            path_values={"owner": "trading", "repo": "lab3", "index": "23"},
        )
        assert binding.batch_bodies == [
            {"index": 22, "owner": "trading", "repo": "lab3"},
            {"index": 21, "owner": "trading", "repo": "lab3"},
        ]

    def test_unrelated_mutations_keep_body_none_without_assignments(self) -> None:
        cap = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]
        binding = bind(
            cap,
            [],
            path_values={"owner": "trading", "repo": "lab3"},
        )
        assert binding.body is None


def _ambiguous() -> Capability:
    document = {
        "swagger": "2.0", "basePath": "/api/v1", "paths": {
            "/things": {"post": {
                "operationId": "createThing",
                "parameters": [
                    {"name": "name", "in": "query", "type": "string"},
                    {"name": "body", "in": "body", "schema": {
                        "type": "object", "properties": {"name": {"type": "string"}}}},
                ],
                "responses": {"201": {"description": "ok", "schema": {"type": "object"}}},
            }},
        },
    }
    return Catalog.from_document(document).by_key["post:/things"]


if __name__ == "__main__":
    unittest.main()
