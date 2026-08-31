"""Classification uses runtime metadata first, the advertised shape second."""

import unittest

from gaxi.classify import classify
from gaxi.transport import Headers, Response


def reply(body: bytes = b"", media_type: str = "", **headers: str) -> Response:
    pairs = [("Content-Type", media_type)] if media_type else []
    pairs += list(headers.items())
    return Response(200, pairs, body=body)


class MediaTypeTest(unittest.TestCase):
    def test_a_json_suffix_counts_as_json(self) -> None:
        result = classify(reply(b"{}", "application/vnd.gitea+json"))
        assert result.kind == "object"

    def test_the_advertised_shape_decides_when_no_type_is_returned(self) -> None:
        assert classify(reply(b"[]"), "collection").kind == "collection"
        assert classify(reply(b"text"), "text").kind == "text"
        assert classify(reply(b"\x00\x01"), "file").kind == "binary"

    def test_declared_text_media_types_are_text(self) -> None:
        assert classify(reply(b"<x/>", "application/xml")).kind == "text"
        assert classify(reply(b"a: 1", "text/yaml")).kind == "text"

    def test_an_empty_body_is_a_status(self) -> None:
        assert classify(reply()).kind == "status"


class JsonTest(unittest.TestCase):
    def test_a_broken_json_body_degrades_to_text(self) -> None:
        result = classify(reply(b"{ not json", "application/json"))
        assert result.kind == "text"
        assert result.decode_error == "response is not valid JSON"
        assert result.media_type == "application/json"

    def test_a_wrapped_collection_is_unwrapped_only_when_advertised(self) -> None:
        body = b'{"data": [1, 2]}'
        assert classify(reply(body, "application/json"), "collection").payload == [1, 2]
        assert classify(reply(body, "application/json"), "object").kind == "object"

    def test_a_wrapper_without_a_list_stays_an_object(self) -> None:
        body = b'{"data": {"a": 1}}'
        assert classify(reply(body, "application/json"), "collection").kind == "object"


class PaginationTest(unittest.TestCase):
    def test_a_server_total_is_reported_as_an_integer(self) -> None:
        result = classify(reply(b"[]", "application/json", **{"X-Total-Count": "17"}), page=1)
        assert result.total == 17

    def test_an_unparsable_total_is_treated_as_absent(self) -> None:
        result = classify(reply(b"[]", "application/json", **{"X-Total-Count": "many"}), page=1)
        assert result.total == "unknown"

    def test_a_link_header_proves_a_next_page(self) -> None:
        link = '<https://gitea.example.com/x?page=2>; rel="next"'
        result = classify(reply(b"[]", "application/json", Link=link), page=1)
        assert result.has_next is True

    def test_without_a_page_an_absent_total_stays_absent(self) -> None:
        assert classify(reply(b"[]", "application/json")).total is None


class StatusTest(unittest.TestCase):
    def test_a_redirect_reports_its_location(self) -> None:
        response = Response(302, Headers([("Location", "https://elsewhere")]))
        result = classify(response)
        assert result.kind == "redirect"
        assert result.payload == "https://elsewhere"

    def test_a_failure_keeps_its_json_payload(self) -> None:
        response = Response(
            404, [("Content-Type", "application/json")], body=b'{"message": "gone"}',
        )
        result = classify(response)
        assert result.kind == "error"
        assert result.payload == {"message": "gone"}

    def test_a_non_json_failure_carries_no_payload(self) -> None:
        response = Response(500, [("Content-Type", "text/html")], body=b"<html>")
        assert classify(response).payload is None

    def test_an_undecodable_body_is_not_json(self) -> None:
        response = Response(
            200, [("Content-Type", "application/json; charset=ascii")], body=b"\xff\xfe",
        )
        assert classify(response).kind == "text"
