"""Invariants of the truncation contract (ADR 0008)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from gaxi.projection import ELLIPSIS, LIMIT, truncate

text = st.text(max_size=LIMIT * 2)


@given(value=text)
def test_truncated_output_never_exceeds_the_limit(value: str) -> None:
    rendered, _ = truncate(value)
    assert len(rendered) <= LIMIT


@given(value=text)
def test_short_values_pass_through_without_a_size_hint(value: str) -> None:
    if len(value) > LIMIT:
        return
    assert truncate(value) == (value, None)


@given(value=st.text(min_size=LIMIT + 1, max_size=LIMIT * 3))
def test_long_values_are_marked_and_report_their_original_length(value: str) -> None:
    rendered, original = truncate(value)
    assert rendered.endswith(ELLIPSIS)
    assert original == len(value)
    assert value.startswith(rendered[: -len(ELLIPSIS)])


@given(value=text)
def test_full_disables_truncation(value: str) -> None:
    assert truncate(value, full=True) == (value, None)
