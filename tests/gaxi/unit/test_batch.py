"""Batch mutations through --input-json arrays and NDJSON."""

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from gaxi.binding import bind
from gaxi.catalog import Catalog
from gaxi.classify import Classification
from gaxi.errors import GaxiError, UsageError
from gaxi.invoke import _batch_error_item, _batch_execution_error_item, _batch_success_item
from gaxi.jsonbody import parse_input_json_bodies
from gaxi.planner import Planner
from gaxi.results import (
    _batch_items_use_declared_fields,
    _batch_result_fields,
    _batch_truncation_help,
    _detail_fields_full_for_row,
    _truncated_fields_by_row,
)
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT
from tests.gaxi.support import json_response, run_cli

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)
CREATE_ISSUE = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]


class ParseInputJsonBodiesTest(unittest.TestCase):
    def test_a_json_array_supplies_multiple_bodies(self) -> None:
        parsed = parse_input_json_bodies(
            CREATE_ISSUE,
            '[{"title": "a"}, {"title": "b"}]',
        )
        assert parsed.is_batch
        assert parsed.bodies == [{"title": "a"}, {"title": "b"}]

    def test_ndjson_skips_blank_lines(self) -> None:
        parsed = parse_input_json_bodies(
            CREATE_ISSUE,
            '{"title": "a"}\n\n{"title": "b"}\n',
        )
        assert parsed.is_batch
        assert parsed.bodies == [{"title": "a"}, {"title": "b"}]

    def test_a_single_object_still_supplies_one_body(self) -> None:
        parsed = parse_input_json_bodies(CREATE_ISSUE, '{"title": "a"}')
        assert not parsed.is_batch
        assert parsed.bodies == [{"title": "a"}]

    def test_a_singleton_json_array_preserves_batch_shape(self) -> None:
        parsed = parse_input_json_bodies(CREATE_ISSUE, '[{"title": "a"}]')
        assert parsed.is_batch
        assert parsed.bodies == [{"title": "a"}]

    def test_array_elements_are_validated(self) -> None:
        with pytest.raises(UsageError) as caught:
            parse_input_json_bodies(CREATE_ISSUE, '[{"title": 1}]')
        assert "title expects string" in caught.value.message

    def test_ndjson_lines_are_validated(self) -> None:
        with pytest.raises(UsageError) as caught:
            parse_input_json_bodies(CREATE_ISSUE, '{"title": "a"}\n{"title": 1}\n')
        assert "title expects string" in caught.value.message

    def test_empty_input_json_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            parse_input_json_bodies(CREATE_ISSUE, "   ")
        assert "empty" in caught.value.message

    def test_an_empty_json_array_supplies_no_bodies(self) -> None:
        parsed = parse_input_json_bodies(CREATE_ISSUE, "[]")
        assert parsed.is_batch
        assert parsed.bodies == []

    def test_ndjson_with_only_blank_lines_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            parse_input_json_bodies(CREATE_ISSUE, "\n\n")
        assert "empty" in caught.value.message

    def test_an_invalid_ndjson_line_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            parse_input_json_bodies(CREATE_ISSUE, '{"title": "a"}\nnot json\n')
        assert "line 2" in caught.value.message

    def test_a_missing_required_property_in_an_array_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            parse_input_json_bodies(CREATE_ISSUE, '[{"body": "no title"}]')
        assert "missing required body property title" in caught.value.message


class BatchItemHelpersTest(unittest.TestCase):
    def test_success_items_cover_non_object_shapes(self) -> None:
        assert _batch_success_item(Classification("status", status=204)) == {"status": 204}
        assert _batch_success_item(Classification("collection", payload=[1, 2])) == {
            "count": 2,
        }
        assert _batch_success_item(Classification("text", payload="hello", status=200)) == {
            "status": 200,
        }

    def test_error_items_copy_response_payload_fields(self) -> None:
        item = _batch_error_item(
            Classification("error", payload={"message": "nope", "errors": ["a"]}, status=422),
        )
        assert item["message"] == "nope"
        assert item["errors"] == ["a"]
        overwritten = _batch_error_item(
            Classification("error", payload={"error": "detail"}, status=400),
        )
        assert overwritten["error"] == "detail"
        plain = _batch_error_item(Classification("error", payload="oops", status=500))
        assert "status 500" in plain["error"]

    def test_error_items_keep_a_canonical_message_when_error_is_falsey(self) -> None:
        item = _batch_error_item(
            Classification("error", payload={"error": ""}, status=422),
        )
        assert item["error"] == "request failed with status 422"
        assert item["status"] == 422
        with_message = _batch_error_item(
            Classification(
                "error",
                payload={"error": "", "message": "validation failed"},
                status=422,
            ),
        )
        assert with_message["error"] == "validation failed"

    def test_execution_error_items_use_the_exception_message(self) -> None:
        item = _batch_execution_error_item(
            GaxiError("cannot reach the instance", status=503),
        )
        assert item == {"error": "cannot reach the instance", "status": 503}
        plain = _batch_execution_error_item(GaxiError("cannot reach the instance"))
        assert plain == {"error": "cannot reach the instance"}


class BindingBatchTest(unittest.TestCase):
    def test_a_json_array_binds_as_batch_bodies(self) -> None:
        binding = bind(CREATE_ISSUE, [], input_json='[{"title": "a"}, {"title": "b"}]')
        assert binding.is_batch()
        assert binding.batch_bodies == [{"title": "a"}, {"title": "b"}]
        assert binding.body is None

    def test_a_singleton_json_array_binds_as_batch(self) -> None:
        binding = bind(CREATE_ISSUE, [], input_json='[{"title": "a"}]')
        assert binding.is_batch()
        assert binding.batch_bodies == [{"title": "a"}]
        assert binding.body is None

    def test_a_single_json_object_binds_as_one_body(self) -> None:
        binding = bind(CREATE_ISSUE, [], input_json='{"title": "a"}')
        assert not binding.is_batch()
        assert binding.body == {"title": "a"}
        assert binding.batch_bodies is None


class RunBatchTest(unittest.TestCase):
    def test_input_json_array_runs_one_request_per_element(self) -> None:
        responses = [
            json_response(
                {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                status=201,
            ),
            json_response(
                {"number": 2, "title": "b", "state": "open", "updated_at": "t"},
                status=201,
            ),
        ]
        code, out, session = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"},{"title":"b"}]',
            ],
            responses=responses,
        )
        assert code == 0
        assert len(support.recorded(session)) == 2
        assert json.loads(support.recorded(session)[0]["body"]) == {"title": "a"}
        assert json.loads(support.recorded(session)[1]["body"]) == {"title": "b"}
        assert "count: 2 of 2 total" in out
        assert "issues[2]" in out

    def test_ndjson_file_runs_one_request_per_line(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            handle.write('{"title": "a"}\n{"title": "b"}\n')
            path = handle.name
        try:
            responses = [
                json_response(
                    {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                    status=201,
                ),
                json_response(
                    {"number": 2, "title": "b", "state": "open", "updated_at": "t"},
                    status=201,
                ),
            ]
            code, out, session = run_cli(
                ["post", "/repos/acme/widgets/issues", "--input-json", "@" + path],
                responses=responses,
            )
        finally:
            Path(path).unlink()
        assert code == 0
        assert len(support.recorded(session)) == 2
        assert "count: 2 of 2 total" in out

    def test_partial_failure_continues_and_exits_nonzero(self) -> None:
        responses = [
            json_response(
                {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                status=201,
            ),
            json_response({"message": "validation failed"}, status=422),
        ]
        code, out, session = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"},{"title":"b"}]',
            ],
            responses=responses,
        )
        assert code == 1
        assert len(support.recorded(session)) == 2
        assert "count: 2 of 2 total" in out
        assert "error" in out
        assert "issues[2]{error,status,number,title}:" in out

    def test_falsey_error_values_still_surface_error_columns(self) -> None:
        responses = [
            json_response(
                {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                status=201,
            ),
            json_response({"error": ""}, status=422),
        ]
        code, out, session = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"},{"title":"b"}]',
            ],
            responses=responses,
        )
        assert code == 1
        assert len(support.recorded(session)) == 2
        assert "issues[2]{error,status,number,title}:" in out
        assert "request failed with status 422" in out

    def test_all_error_batch_renders_error_columns(self) -> None:
        responses = [
            json_response({"message": "bad"}, status=422),
            json_response({"message": "worse"}, status=422),
        ]
        code, out, session = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"},{"title":"b"}]',
            ],
            responses=responses,
        )
        assert code == 1
        assert len(support.recorded(session)) == 2
        assert "count: 2 of 2 total" in out
        assert "issues[2]{error,status}:" in out
        assert "bad,422" in out
        assert "worse,422" in out

    def test_delete_batch_mixed_204_404_renders_error_columns(self) -> None:
        responses = [
            support.response(204, b""),
            json_response({"message": "comment not found"}, status=404),
        ]
        code, out, session = run_cli(
            [
                "delete",
                "/repos/acme/widgets/issues/comments/17",
                "--yes",
                "--input-json",
                "[{},{}]",
            ],
            responses=responses,
        )
        assert code == 1
        assert len(support.recorded(session)) == 2
        assert "count: 2 of 2 total" in out
        assert "comment[2]{error,status}:" in out
        assert "null,204" in out
        assert "comment not found,404" in out

    def test_collection_batch_elements_render_count_not_blank_rows(self) -> None:
        responses = [
            json_response(
                [
                    {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                    {"number": 2, "title": "b", "state": "open", "updated_at": "t"},
                ],
            ),
            json_response(
                [{"number": 3, "title": "c", "state": "closed", "updated_at": "t"}],
            ),
        ]
        code, out, session = run_cli(
            [
                "get",
                "/repos/acme/widgets/pulls",
                "--input-json",
                "[{},{}]",
            ],
            responses=responses,
        )
        assert code == 0
        assert len(support.recorded(session)) == 2
        assert "count: 2 of 2 total" in out
        assert "pull_requests[2]{count}:" in out
        assert "2" in out
        assert "1" in out

    def test_destructive_batch_retry_help_quotes_shell_metacharacters(self) -> None:
        payload = '[{"title":"$(printf INJECTED)"}]'
        code, out, session = run_cli(
            [
                "delete",
                "/repos/acme/widgets/issues/comments/17",
                "--input-json",
                payload,
            ],
        )
        assert code == 1
        assert "requires --yes" in out
        assert support.recorded(session) == []
        assert (
            "- gaxi delete /repos/acme/widgets/issues/comments/17 "
            "--input-json '[{\"title\":\"$(printf INJECTED)\"}]' --yes"
        ) in out

    def test_destructive_batch_retry_help_keeps_an_input_json_file_reference(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            handle.write('{"title": "a"}\n{"title": "b"}\n')
            path = handle.name
        try:
            code, out, session = run_cli(
                [
                    "delete",
                    "/repos/acme/widgets/issues/comments/17",
                    "--input-json",
                    "@" + path,
                ],
            )
        finally:
            Path(path).unlink()
        assert code == 1
        assert "requires --yes" in out
        assert support.recorded(session) == []
        assert (
            f"- gaxi delete /repos/acme/widgets/issues/comments/17 "
            f"--input-json @{path} --yes"
        ) in out

    def test_destructive_batch_retry_help_preserves_input_json(self) -> None:
        payload = "[{},{}]"
        code, out, session = run_cli(
            [
                "delete",
                "/repos/acme/widgets/issues/comments/17",
                "--input-json",
                payload,
            ],
        )
        assert code == 1
        assert "requires --yes" in out
        assert support.recorded(session) == []
        assert (
            f"- gaxi delete /repos/acme/widgets/issues/comments/17 "
            f"--input-json {payload} --yes"
        ) in out

    def test_execution_failure_continues_through_the_batch(self) -> None:
        responses = [
            json_response(
                {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                status=201,
            ),
            json_response(
                {"number": 2, "title": "b", "state": "open", "updated_at": "t"},
                status=201,
            ),
        ]
        code, out, session = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"},{"title":"b"},{"title":"c"}]',
            ],
            responses=responses,
        )
        assert code == 1
        assert len(support.recorded(session)) == 3
        assert "count: 3 of 3 total" in out
        assert "no scripted response" in out
        assert "issues[3]{error,status,number,title}:" in out

    def test_a_singleton_json_array_runs_as_batch(self) -> None:
        code, out, session = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"}]',
            ],
            responses=[
                json_response(
                    {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                    status=201,
                ),
            ],
        )
        assert code == 0
        assert len(support.recorded(session)) == 1
        assert "count: 1 of 1 total" in out
        assert "issues[1]" in out

    def test_batch_requests_reject_save_and_raw_on_singleton_arrays(self) -> None:
        code, out, _ = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"}]',
                "--raw",
            ],
            responses=[],
        )
        assert code == 2
        assert "batch requests cannot use --save or --raw" in out

    def test_batch_requests_reject_save_and_raw(self) -> None:
        code, out, _ = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"},{"title":"b"}]',
                "--raw",
            ],
            responses=[],
        )
        assert code == 2
        assert "batch requests cannot use --save or --raw" in out

    def test_an_empty_array_batch_sends_no_requests(self) -> None:
        code, out, session = run_cli(
            ["post", "/repos/acme/widgets/issues", "--input-json", "[]"],
        )
        assert code == 0
        assert len(support.recorded(session)) == 0
        assert "count: 0" in out

    def test_dry_run_lists_batch_body_inputs(self) -> None:
        code, out, _ = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                '[{"title":"a"},{"title":"b"}]',
                "--dry-run",
            ],
        )
        assert code == 0
        assert "[0].title" in out
        assert "[1].title" in out

    def test_batch_body_rows_handle_non_object_values(self) -> None:
        binding = bind(
            CATALOG.by_key["get:/repos/{owner}/{repo}/pulls"],
            [],
            input_json="[1, 2]",
        )
        assert binding.is_batch()
        assert binding.batch_bodies == [1, 2]

    def test_dry_run_shows_non_object_batch_values(self) -> None:
        code, out, _ = run_cli(
            [
                "get",
                "/repos/acme/widgets/pulls",
                "--input-json",
                "[1, 2]",
                "--dry-run",
            ],
        )
        assert code == 0
        assert "[0]" in out
        assert "[1]" in out

    def test_batch_truncation_suggests_detail_retrieval_not_mutation_replay(self) -> None:
        long_title = "x" * 200
        responses = [
            json_response(
                {
                    "number": 1,
                    "title": long_title,
                    "state": "open",
                    "updated_at": "t",
                },
                status=201,
            ),
            json_response(
                {
                    "number": 2,
                    "title": "b",
                    "state": "open",
                    "updated_at": "t",
                },
                status=201,
            ),
        ]
        code, out, _ = run_cli(
            [
                "post",
                "/repos/acme/widgets/issues",
                "--input-json",
                f'[{{"title":"{long_title}"}},{{"title":"b"}}]',
                "--fields",
                "title",
            ],
            responses=responses,
        )
        assert code == 0
        assert "truncated" in out
        assert "- gaxi get /repos/acme/widgets/issues/1 --fields title --full" in out
        assert "gaxi post /repos/acme/widgets/issues" not in out


class BatchTruncationHelpTest(unittest.TestCase):
    def test_duplicate_truncation_fields_are_deduplicated(self) -> None:
        by_row = _truncated_fields_by_row([(1, "title", 200), (1, "title", 200)])
        assert by_row == {1: ["title"]}

    def test_out_of_range_rows_are_skipped(self) -> None:
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            bind(CREATE_ISSUE, [], input_json='[{"title":"a"}]'),
        )
        assert _detail_fields_full_for_row(planner, [], 1, ["title"]) is None
        assert _detail_fields_full_for_row(planner, [{"number": 1}], 0, ["title"]) is None

    def test_non_dict_rows_are_skipped(self) -> None:
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            bind(CREATE_ISSUE, [], input_json='[{"title":"a"}]'),
        )
        assert _detail_fields_full_for_row(planner, ["not a dict"], 1, ["title"]) is None

    def test_unresolvable_entities_produce_no_suggestions(self) -> None:
        planner = Planner(
            CATALOG,
            CREATE_ISSUE,
            "/repos/acme/widgets/issues",
            bind(CREATE_ISSUE, [], input_json='[{"title":"a"}]'),
        )
        assert _batch_truncation_help(planner, [{}], [(1, "title", 200)]) == []


class BatchResultFieldsTest(unittest.TestCase):
    def test_empty_declared_schema_does_not_match_batch_rows(self) -> None:
        assert not _batch_items_use_declared_fields([{"count": 1}], [])

    def test_falsey_error_values_still_prefer_error_columns(self) -> None:
        fields = _batch_result_fields(
            ["number", "title", "state", "updated_at"],
            [
                {"number": 1, "title": "a", "state": "open", "updated_at": "t"},
                {"error": "", "status": 422},
            ],
        )
        assert fields == ["error", "status", "number", "title"]

    def test_observed_error_columns_are_retained_for_all_error_batches(self) -> None:
        fields = _batch_result_fields(
            ["status", "error"],
            [
                {"error": "first", "status": 422},
                {"error": "second", "status": 422},
            ],
        )
        assert fields == ["error", "status"]

    def test_observed_error_columns_are_retained_for_status_only_success_rows(self) -> None:
        fields = _batch_result_fields(
            ["status", "error"],
            [
                {"status": 204},
                {"error": "not found", "status": 404},
            ],
        )
        assert fields == ["error", "status"]
