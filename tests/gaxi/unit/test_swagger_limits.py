"""Unsupported Swagger constructs disable one capability, never the catalog."""

import unittest

import pytest

from gaxi.capability import Capability, UnsupportedError
from gaxi.catalog import Catalog
from gaxi.swagger import Description, compile_description
from tests.gaxi import support

BASE = {"swagger": "2.0", "basePath": "/api/v1", "info": {"title": "t", "version": "1"}}


def document(paths: dict[str, object], **extra: object) -> dict[str, object]:
    return {**BASE, "paths": paths, **extra}


def only(raw: dict[str, object]) -> Capability:
    capabilities, _ = compile_description(raw)
    assert len(capabilities) == 1
    return capabilities[0]


def reason(raw: dict[str, object]) -> str:
    cap = only(raw)
    assert cap.unsupported is not None
    return cap.unsupported


class ReferenceTest(unittest.TestCase):
    def test_an_external_reference_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedError) as caught:
            Description(BASE).resolve({"$ref": "other.json#/Thing"})
        assert "external reference" in caught.value.args[0]

    def test_an_unresolvable_reference_is_unsupported(self) -> None:
        with pytest.raises(UnsupportedError) as caught:
            Description(BASE).resolve({"$ref": "#/definitions/Absent"})
        assert "unresolvable reference" in caught.value.args[0]

    def test_a_cyclic_reference_is_bounded(self) -> None:
        raw = {**BASE, "definitions": {"Loop": {"$ref": "#/definitions/Loop"}}}
        with pytest.raises(UnsupportedError) as caught:
            Description(raw).resolve({"$ref": "#/definitions/Loop"})
        assert "cyclic reference" in caught.value.args[0]

    def test_escaped_pointer_segments_are_decoded(self) -> None:
        raw = {**BASE, "paths": {"/a~b/c": {"x": 1}}}
        resolved = Description(raw).resolve({"$ref": "#/paths/~1a~0b~1c"})
        assert resolved == {"x": 1}


class ParameterTest(unittest.TestCase):
    def test_a_parameter_without_a_name_disables_the_capability(self) -> None:
        cap = only(document({"/x": {"get": {"parameters": [{"in": "query"}]}}}))
        assert cap.available is False
        assert cap.unsupported is not None
        assert "without a name or location" in cap.unsupported

    def test_an_unsupported_location_disables_the_capability(self) -> None:
        raw = document({"/x": {"get": {"parameters": [{"name": "n", "in": "cookie"}]}}})
        assert "unsupported parameter location cookie" in reason(raw)

    def test_an_unsupported_type_disables_the_capability(self) -> None:
        raw = document({"/x": {"get": {
            "parameters": [{"name": "n", "in": "query", "type": "object"}]}}})
        assert "unsupported parameter type" in reason(raw)

    def test_an_unsupported_array_item_type_disables_the_capability(self) -> None:
        raw = document({"/x": {"get": {"parameters": [
            {"name": "n", "in": "query", "type": "array", "items": {"type": "object"}}]}}})
        assert "unsupported array item type" in reason(raw)

    def test_an_undeclared_path_parameter_disables_the_capability(self) -> None:
        assert "undeclared path parameter id" in reason(document({"/x/{id}": {"get": {}}}))


class ResponseTest(unittest.TestCase):
    def test_a_non_integer_status_is_ignored(self) -> None:
        cap = only(document({"/x": {"get": {"responses": {"default": {"description": "d"}}}}}))
        assert cap.responses == {}

    def test_a_text_producing_operation_reports_text(self) -> None:
        raw = document({"/x": {"get": {
            "produces": ["text/plain"],
            "responses": {"200": {"description": "d", "schema": {"type": "object"}}},
        }}})
        spec = only(raw).success_response()
        assert spec is not None
        assert spec.kind == "text"

    def test_a_response_without_a_schema_is_named_by_its_status(self) -> None:
        raw = document({"/x": {"get": {"responses": {
            "204": {"description": "gone"},
            "418": {"description": "odd"},
        }}}})
        cap = only(raw)
        assert cap.responses[204].kind == "empty"
        assert cap.responses[418].kind == "unknown"


class CatalogShapeTest(unittest.TestCase):
    def test_non_operation_keys_are_skipped(self) -> None:
        raw = document({
            "/x": {"get": {}, "parameters": [], "x-extension": {"ignored": True}},
            "/broken": "not a path item",
        })
        capabilities, _ = compile_description(raw)
        assert [cap.key for cap in capabilities] == ["get:/x"]

    def test_the_root_path_compiles_to_a_root_matcher(self) -> None:
        catalog = Catalog.from_document(document({"/": {"get": {}}}), origin=support.ORIGIN)
        assert catalog.match("get", "/")
        assert catalog.match("get", "/other") == []
