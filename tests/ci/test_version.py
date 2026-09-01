"""Semantic version arithmetic."""

import unittest

import pytest

from ci import version as v
from ci.version import Version


class ParseTest(unittest.TestCase):
    def test_a_version_round_trips_through_its_text(self) -> None:
        assert str(Version.parse("1.2.3")) == "1.2.3"

    def test_surrounding_whitespace_is_tolerated(self) -> None:
        assert str(Version.parse("  1.2.3\n")) == "1.2.3"

    def test_anything_that_is_not_three_numbers_is_rejected(self) -> None:
        for text in ["1.2", "1.2.3.4", "v1.2.3", "1.2.3-rc1", ""]:
            with pytest.raises(ValueError, match="not a version"):
                Version.parse(text)


class BumpTest(unittest.TestCase):
    def test_each_level_zeroes_the_levels_below_it(self) -> None:
        version = Version.parse("1.4.7")
        assert str(version.bumped(v.MAJOR)) == "2.0.0"
        assert str(version.bumped(v.MINOR)) == "1.5.0"
        assert str(version.bumped(v.PATCH)) == "1.4.8"

    def test_an_unknown_level_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a bump level"):
            Version.parse("1.0.0").bumped("enormous")
