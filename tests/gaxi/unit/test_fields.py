"""Field-selection precedence for one capability response."""

import unittest

import pytest

from gaxi.capability import Capability, ResponseSpec
from gaxi.errors import UsageError
from gaxi.fields import fields
from gaxi.policy import Properties


def _cap(*, schema: dict[str, object] | None = None) -> Capability:
    responses: dict[int, ResponseSpec] = {200: ResponseSpec(status=200, kind="object")}
    if schema is not None:
        responses[200] = ResponseSpec(status=200, kind="object", schema=schema)
    return Capability(method="get", path="/x", responses=responses)


class FieldsPrecedenceTest(unittest.TestCase):
    def test_selected_fields_win_after_validation(self) -> None:
        cap = _cap(schema={"type": "object", "properties": {"id": {"type": "integer"}}})
        props = Properties()
        props.projection = ["name"]
        items = [{"id": 1, "name": "one"}]
        assert fields(cap, props, items, ["name", "id"]) == ["name", "id"]

    def test_unknown_selected_field_is_rejected(self) -> None:
        cap = _cap()
        props = Properties()
        with pytest.raises(UsageError):
            fields(cap, props, [{"id": 1}], ["missing"])

    def test_policy_projection_is_filtered_to_available_fields(self) -> None:
        cap = _cap(schema={
            "type": "object",
            "properties": {"number": {"type": "integer"}, "title": {"type": "string"}},
        })
        props = Properties()
        props.projection = ["number", "title", "missing"]
        items = [{"number": 1, "title": "Fix"}]
        assert fields(cap, props, items, None) == ["number", "title"]

    def test_policy_projection_survives_when_nothing_is_available(self) -> None:
        cap = _cap()
        props = Properties()
        props.projection = ["name"]
        assert fields(cap, props, [1, 2], None) == ["name"]

    def test_dotted_policy_projection_survives_empty_collections(self) -> None:
        cap = _cap(schema={
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "body": {"type": "string"},
                "user": {"type": "object"},
                "created_at": {"type": "string"},
            },
        })
        props = Properties()
        props.projection = ["id", "user.login", "body", "created_at"]
        assert fields(cap, props, [], None) == ["id", "user.login", "body", "created_at"]

    def test_observed_fields_use_fallback_ranking(self) -> None:
        cap = _cap()
        props = Properties()
        items = [{"created_at": "t", "state": "open", "title": "Fix", "id": 3}]
        assert fields(cap, props, items, None) == ["id", "title", "state", "created_at"]

    def test_declared_schema_names_cap_the_empty_response(self) -> None:
        cap = _cap(schema={
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "integer"},
                "c": {"type": "boolean"},
                "d": {"type": "number"},
                "e": {"type": "string"},
            },
        })
        props = Properties()
        assert fields(cap, props, [], None) == ["a", "b", "c", "d"]
