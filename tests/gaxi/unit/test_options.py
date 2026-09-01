"""Frozen options: coercion, grouping, and seam separation."""

import unittest

import pytest

from gaxi import cli
from gaxi.errors import UsageError
from gaxi.options import DiscoveryOptions, Options, RequestOptions, build_options


class BuildOptionsTest(unittest.TestCase):
    def test_path_and_save_map_to_different_groups(self) -> None:
        options = build_options({"save": "out.bin", "path": "skill.md"})
        assert options.request.save == "out.bin"
        assert options.setup.path == "skill.md"

    def test_fields_are_coerced_to_a_tuple(self) -> None:
        options = build_options({"fields": "a, b ,,c"})
        assert options.request.fields == ("a", "b", "c")

    def test_fields_accept_pre_coerced_sequences(self) -> None:
        assert build_options({"fields": ("x", "y")}).request.fields == ("x", "y")
        assert build_options({"fields": ["p", "q"]}).request.fields == ("p", "q")

    def test_tuple_field_members_are_coerced_to_strings(self) -> None:
        options = build_options({"fields": (1, "b")})
        assert options.request.fields == ("1", "b")

    def test_non_integer_timeout_values_are_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            build_options({"timeout": "abc"})
        assert "expects an integer" in caught.value.message

    def test_boolean_timeout_values_are_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            build_options({"timeout": True})
        assert "expects an integer" in caught.value.message

    def test_unknown_output_formats_are_rejected(self) -> None:
        with pytest.raises(UsageError) as caught:
            build_options({"output": "xml"})
        assert "unknown output format xml" in caught.value.message


class ParsePathTest(unittest.TestCase):
    def test_setup_path_does_not_set_request_save(self) -> None:
        options = cli.parse(["setup", "skill", "--path", "SKILL.md"]).options
        assert options.setup.path == "SKILL.md"
        assert options.request.save is None

    def test_request_save_does_not_set_setup_path(self) -> None:
        options = cli.parse(["get", "/x", "--save", "out.bin"]).options
        assert options.request.save == "out.bin"
        assert options.setup.path is None


class ImmutabilityTest(unittest.TestCase):
    def test_options_are_frozen(self) -> None:
        options = Options(request=RequestOptions(save="x"))
        with pytest.raises(AttributeError):
            options.request = RequestOptions()  # type: ignore[misc]

    def test_discovery_options_are_frozen(self) -> None:
        options = Options(discovery=DiscoveryOptions(debug=True))
        with pytest.raises(AttributeError):
            options.discovery.debug = False  # type: ignore[misc]
