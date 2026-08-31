import unittest
from typing import override

import pytest

from gaxi.catalog import Catalog
from gaxi.errors import GaxiError, UsageError
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT


class CompileTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.catalog = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)

    def test_every_capability_has_a_unique_key(self) -> None:
        keys = [cap.key for cap in self.catalog.capabilities]
        assert len(keys) == len(set(keys))

    def test_references_are_resolved(self) -> None:
        cap = self.catalog.by_key["get:/repos/{owner}/{repo}/pulls"]
        spec = cap.success_response()
        assert spec is not None
        assert spec.kind == "collection"
        assert spec.entity_ref == "PullRequest"

    def test_parameter_locations_and_types(self) -> None:
        cap = self.catalog.by_key["get:/repos/{owner}/{repo}/pulls"]
        by_name = {p.name: p for p in cap.params}
        assert by_name["owner"].location == "path"
        assert by_name["state"].enum == ["open", "closed", "all"]
        assert by_name["labels"].is_array
        assert by_name["labels"].items_type == "integer"

    def test_body_schema_is_resolved(self) -> None:
        cap = self.catalog.by_key["post:/repos/{owner}/{repo}/issues"]
        assert cap.body is not None
        assert cap.body.schema is not None
        assert sorted(cap.body.schema["properties"]) == ["body", "closed", "labels", "title"]

    def test_response_kinds(self) -> None:
        kinds = {
            "get:/repos/{owner}/{repo}/pulls/{index}.{diffType}": "text",
            "get:/repos/{owner}/{repo}/archive/{archive}": "file",
            "delete:/repos/{owner}/{repo}/issues/comments/{id}": "empty",
            "get:/repos/{owner}/{repo}/redirect": "redirect",
            "get:/repos/{owner}/{repo}/pulls/{index}": "object",
        }
        for key, kind in kinds.items():
            spec = self.catalog.by_key[key].success_response()
            assert spec is not None, key
            assert spec.kind == kind, key

    def test_file_upload_parameter(self) -> None:
        cap = self.catalog.by_key["post:/repos/{owner}/{repo}/releases/{id}/assets"]
        param = next(p for p in cap.params if p.name == "attachment")
        assert param.is_file
        assert param.binding_location == "form"

    def test_unsupported_construct_disables_only_its_capability(self) -> None:
        unavailable = {cap.key for cap in self.catalog.unavailable()}
        assert unavailable == {"get:/admin/unsupported", "get:/admin/broken"}
        assert self.catalog.by_key["get:/user"].available


class ResolutionTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.catalog = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)

    def test_unique_match(self) -> None:
        cap, values = self.catalog.resolve("get", "/repos/acme/widgets/pulls")
        assert cap.operation_id == "repoListPullRequests"
        assert values == {"owner": "acme", "repo": "widgets"}

    def test_static_segments_beat_parameter_segments(self) -> None:
        cap, _ = self.catalog.resolve("get", "/repos/search")
        assert cap.operation_id == "repoSearch"

    def test_partially_templated_segment(self) -> None:
        cap, values = self.catalog.resolve("get", "/repos/acme/widgets/pulls/42.diff")
        assert cap.operation_id == "repoDownloadPullDiffOrPatch"
        assert values["diffType"] == "diff"

    def test_no_match_is_an_ordinary_failure(self) -> None:
        with pytest.raises(GaxiError) as caught:
            self.catalog.resolve("get", "/nope/here")
        assert caught.value.exit_code == 1
        assert "no advertised capability" in caught.value.message

    def test_ambiguous_match_lists_candidates_without_a_request(self) -> None:
        with pytest.raises(GaxiError) as caught:
            self.catalog.resolve("get", "/org/acme/widgets")
        assert caught.value.exit_code == 1
        assert len(caught.value.help_commands) == 2
        assert "--as get:/org/{org}/widgets" in caught.value.help_commands[0]

    def test_selector_disambiguates(self) -> None:
        cap, values = self.catalog.resolve("get", "/org/acme/widgets",
                                           selector="get:/org/{owner}/widgets")
        assert cap.operation_id == "orgListWidgetsAlias"
        assert values == {"owner": "acme"}

    def test_operation_id_selector(self) -> None:
        cap, _ = self.catalog.resolve("get", "/org/acme/widgets",
                                      selector="orgListWidgets")
        assert cap.operation_id == "orgListWidgets"

    def test_selector_that_does_not_match_the_request_fails(self) -> None:
        with pytest.raises(UsageError):
            self.catalog.resolve("get", "/repos/acme/widgets/pulls",
                                 selector="userGetCurrent")

    def test_unavailable_capability_reports_its_reason(self) -> None:
        with pytest.raises(GaxiError) as caught:
            self.catalog.resolve("get", "/admin/unsupported")
        assert "unavailable" in caught.value.message

    def test_search_filters_across_metadata(self) -> None:
        found = {cap.key for cap in self.catalog.search(["pull"])}
        assert "get:/repos/{owner}/{repo}/pulls" in found
        assert "get:/user" not in found


if __name__ == "__main__":
    unittest.main()
