"""Invariants of TOON scalar rendering."""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from gaxi.encode import format_value

scalar_text = st.text(
    alphabet=st.characters(exclude_categories=("Cs", "Cc")) | st.sampled_from("\n\r\t"),
    max_size=50,
)


@given(value=scalar_text)
def test_quoted_rendering_round_trips_through_json(value: str) -> None:
    assert json.loads(format_value(value, quoted=True)) == value


@given(value=scalar_text)
def test_rendered_scalars_never_contain_a_raw_line_break(value: str) -> None:
    assert "\n" not in format_value(value)
    assert "\r" not in format_value(value)


@given(value=scalar_text)
def test_row_cells_containing_a_delimiter_are_quoted(value: str) -> None:
    rendered = format_value(value, in_row=True)
    assert "," not in rendered or rendered.startswith('"')


@given(value=st.integers() | st.booleans() | st.none())
def test_non_strings_are_never_quoted(value: int | bool | None) -> None:
    assert not format_value(value).startswith('"')
