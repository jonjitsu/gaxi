"""Command-line parsing: options, values, and the failures they produce."""

import io
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import override

import pytest

from gaxi import cli
from gaxi.errors import EXIT_FAILURE, EXIT_USAGE, GaxiError, UsageError
from tests.gaxi.support import run_cli


class ParseTest(unittest.TestCase):
    def test_a_bare_command_line_parses_to_nothing(self) -> None:
        invocation = cli.parse([])
        assert invocation.name is None
        assert invocation.positionals == []
        assert invocation.wants_help is False
        assert invocation.wants_version is False

    def test_help_and_version_are_recognised_anywhere(self) -> None:
        assert cli.parse(["get", "-h"]).wants_help is True
        assert cli.parse(["--version"]).wants_version is True

    def test_inline_and_separate_option_values_agree(self) -> None:
        inline = cli.parse(["get", "/x", "--output=json"]).options
        separate = cli.parse(["get", "/x", "--output", "json"]).options
        assert inline.output.format == separate.output.format == "json"

    def test_a_flag_rejects_a_value(self) -> None:
        with pytest.raises(UsageError) as caught:
            cli.parse(["--full=yes"])
        assert "does not take a value" in caught.value.message

    def test_a_value_option_requires_one(self) -> None:
        with pytest.raises(UsageError) as caught:
            cli.parse(["get", "/x", "--output"])
        assert "--output requires a value" in caught.value.message

    def test_unknown_options_are_rejected_in_both_forms(self) -> None:
        with pytest.raises(UsageError) as caught:
            cli.parse(["--nope"])
        assert caught.value.exit_code == EXIT_USAGE
        with pytest.raises(UsageError) as caught:
            cli.parse(["-x"])
        assert "unknown option -x" in caught.value.message

    def test_a_negative_number_is_a_positional_not_an_option(self) -> None:
        assert cli.parse(["get", "/x", "-1"]).positionals == ["/x", "-1"]

    def test_fields_are_split_and_stripped(self) -> None:
        assert cli.parse(["--fields", "a, b ,,c"]).options.request.fields == ("a", "b", "c")

    def test_integer_options_must_be_positive_integers(self) -> None:
        assert cli.parse(["--timeout", "5"]).options.discovery.timeout == 5
        with pytest.raises(UsageError) as caught:
            cli.parse(["--limit", "abc"])
        assert "expects an integer" in caught.value.message
        with pytest.raises(UsageError) as caught:
            cli.parse(["--page", "0"])
        assert "expects a positive integer" in caught.value.message

    def test_an_unknown_output_format_is_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            cli.parse(["--output", "xml"])
        assert "unknown output format xml" in caught.value.message


class InputJsonTest(unittest.TestCase):
    def test_a_literal_value_is_used_as_written(self) -> None:
        parsed = cli.parse(["--input-json", '{"a": 1}'])
        assert parsed.options.request.input_json == '{"a": 1}'
        assert parsed.options.request.input_json_source == '{"a": 1}'

    def test_a_dash_reads_standard_input(self) -> None:
        with unittest.mock.patch.object(sys, "stdin", io.StringIO('{"a": 1}')):
            assert cli.parse(["--input-json", "-"]).options.request.input_json == '{"a": 1}'

    def test_an_at_prefix_reads_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "body.json"
            path.write_text('{"a": 1}', encoding="utf-8")
            parsed = cli.parse(["--input-json", f"@{path}"])
            assert parsed.options.request.input_json == '{"a": 1}'
            assert parsed.options.request.input_json_source == f"@{path}"

    def test_an_unreadable_file_is_a_usage_failure(self) -> None:
        with pytest.raises(UsageError) as caught:
            cli.parse(["--input-json", "@/nonexistent/body.json"])
        assert "cannot read --input-json file" in caught.value.message


class DispatchTest(unittest.TestCase):
    def test_a_verb_without_a_path_is_a_usage_failure(self) -> None:
        code, out, _ = run_cli(["get"])
        assert code == EXIT_USAGE
        assert "get requires one API-relative path" in out

    def test_capability_requires_exactly_one_selector(self) -> None:
        code, out, _ = run_cli(["capability"])
        assert code == EXIT_USAGE
        assert "capability requires one key or operationId" in out

    def test_an_unknown_command_lists_the_known_ones(self) -> None:
        code, out, _ = run_cli(["frobnicate"])
        assert code == EXIT_USAGE
        assert "unknown command frobnicate" in out
        assert "capabilities" in out

    def test_every_command_has_help(self) -> None:
        for name in ("capabilities", "capability", "context", "skill", "setup", "auth", "get"):
            code, out, _ = run_cli([name, "--help"])
            assert code == 0, name
            assert "usage:" in out, name


class OutputTest(unittest.TestCase):
    def test_an_interrupt_is_reported_as_a_structured_failure(self) -> None:
        with unittest.mock.patch.object(cli, "dispatch", side_effect=KeyboardInterrupt):
            code, out, _ = run_cli(["context"])
        assert code == EXIT_FAILURE
        assert "  message: interrupted" in out

    def test_a_failure_before_a_session_exists_still_renders(self) -> None:
        stream = io.StringIO()
        with unittest.mock.patch.object(cli, "parse", side_effect=GaxiError("broken")):
            code = cli.main(["context"], stdout=stream)
        assert code == EXIT_FAILURE
        assert "  message: broken" in stream.getvalue()

    def test_raw_output_uses_the_byte_buffer_when_there_is_one(self) -> None:
        class Streams(io.StringIO):
            def __init__(self) -> None:
                super().__init__()
                self.bytes = io.BytesIO()

            @property
            @override
            def buffer(self) -> io.BytesIO:
                return self.bytes

        stream = Streams()
        cli._write_raw(stream, b"payload")
        assert stream.bytes.getvalue() == b"payload"
        assert stream.getvalue() == ""

    def test_raw_output_falls_back_to_text(self) -> None:
        stream = io.StringIO()
        cli._write_raw(stream, b"payload")
        assert stream.getvalue() == "payload"
