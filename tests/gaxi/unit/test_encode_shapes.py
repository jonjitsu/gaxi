"""Encoder edge cases: unknown nodes, empty containers, and format selection."""

import unittest

import pytest

from gaxi.document import Aggregate, CommaList, Document, Lines, Mapping, Node, Scalar, Table
from gaxi.encode import encode, format_value, to_json, to_toon, to_yaml


class UnknownNodeTest(unittest.TestCase):
    def test_toon_refuses_a_node_it_does_not_know(self) -> None:
        document = Document([("x", Node())])
        with pytest.raises(TypeError) as caught:
            to_toon(document)
        assert "unsupported node" in str(caught.value)

    def test_the_object_form_refuses_it_too(self) -> None:
        document = Document([("x", Node())])
        with pytest.raises(TypeError) as caught:
            to_json(document)
        assert "unsupported node" in str(caught.value)


class NestingTest(unittest.TestCase):
    def test_nested_mappings_round_trip_through_every_format(self) -> None:
        inner = Mapping().add("depth", 2)
        document = Document().add("outer", Mapping().add("inner", inner))
        assert to_toon(document) == "outer:\n  inner:\n    depth: 2"
        assert to_yaml(document) == "outer:\n  inner:\n    depth: 2"
        assert '"depth": 2' in to_json(document)

    def test_empty_containers_are_rendered_explicitly_in_yaml(self) -> None:
        document = Document().add("empty_table", Table(["a"], [])).add("empty", Mapping())
        assert to_yaml(document) == "empty_table: []\nempty: {}"

    def test_a_list_of_objects_is_indented_under_its_dash(self) -> None:
        document = Document().add("rows", Table(["a", "b"], [[1, 2], [3, 4]]))
        assert to_yaml(document) == "rows:\n  - a: 1\n    b: 2\n  - a: 3\n    b: 4"

    def test_lines_are_rendered_as_items(self) -> None:
        document = Document().add("help", Lines(["one", "two"]))
        assert to_toon(document) == "help[2]:\n  - one\n  - two"
        assert to_yaml(document) == 'help:\n  - "one"\n  - "two"'

    def test_comma_lists_render_on_one_line(self) -> None:
        document = Document().add("omitted", CommaList(["body", "created_at"]))
        assert to_toon(document) == "omitted[2]: body, created_at"
        assert to_yaml(document) == 'omitted:\n  - "body"\n  - "created_at"'

    def test_comma_lists_escape_delimiters_and_control_characters(self) -> None:
        document = Document().add(
            "omitted",
            CommaList(["two,fields", "line\nbreak", "tab\there"]),
        )
        assert to_toon(document) == (
            'omitted[3]: "two,fields", "line\\nbreak", "tab\\there"'
        )
        assert to_yaml(document) == (
            'omitted:\n  - "two,fields"\n  - "line\\nbreak"\n  - "tab\\there"'
        )

    def test_comma_lists_quote_primitive_looking_field_names(self) -> None:
        document = Document().add(
            "omitted",
            CommaList(["true", "42", "null", "false", "-", ""]),
        )
        assert to_toon(document) == (
            'omitted[6]: "true", "42", "null", "false", "-", ""'
        )
        assert to_yaml(document) == (
            'omitted:\n'
            '  - "true"\n'
            '  - "42"\n'
            '  - "null"\n'
            '  - "false"\n'
            '  - "-"\n'
            '  - ""'
        )


class ScalarTest(unittest.TestCase):
    def test_yaml_scalars_keep_their_json_types(self) -> None:
        document = Document().add("n", None).add("t", True).add("f", False).add("i", 3)
        assert to_yaml(document) == "n: null\nt: true\nf: false\ni: 3"

    def test_yaml_strings_are_quoted(self) -> None:
        assert to_yaml(Document().add("s", "text")) == 's: "text"'

    def test_ambiguous_strings_are_quoted_in_toon(self) -> None:
        assert format_value("true") == '"true"'
        assert format_value("3.5") == '"3.5"'
        assert format_value(" padded ") == '" padded "'
        assert format_value("plain") == "plain"

    def test_row_cells_only_quote_what_would_break_the_row(self) -> None:
        assert format_value("true", in_row=True) == "true"
        assert format_value("a,b", in_row=True) == '"a,b"'

    def test_floats_keep_their_representation(self) -> None:
        assert format_value(1.5) == "1.5"


class AggregateTest(unittest.TestCase):
    def test_an_empty_collection_reports_a_bare_zero(self) -> None:
        assert to_toon(Document().add("count", Aggregate(0))) == "count: 0"

    def test_an_unknown_total_is_named(self) -> None:
        rendered = to_toon(Document().add("count", Aggregate(2, "unknown")))
        assert rendered == "count: 2\ntotal: unknown"

    def test_a_known_total_is_reported_inline(self) -> None:
        assert to_toon(Document().add("count", Aggregate(2, 17))) == "count: 2 of 17 total"

    def test_the_object_form_lifts_the_total(self) -> None:
        assert '"total": 17' in to_json(Document().add("count", Aggregate(2, 17)))


class FormatSelectionTest(unittest.TestCase):
    def test_every_advertised_format_is_reachable(self) -> None:
        document = Document().add("x", Scalar(1))
        assert encode(document, "toon") == "x: 1"
        assert encode(document, "json") == '{\n  "x": 1\n}'
        assert encode(document, "yaml") == "x: 1"

    def test_an_unknown_format_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="unknown output format"):
            encode(Document(), "xml")
