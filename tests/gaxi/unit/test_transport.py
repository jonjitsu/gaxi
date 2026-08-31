"""The HTTP exchange: header handling, scheme policy, and failure mapping."""

import http.client
import io
import unittest
import urllib.error
from email.message import Message
from typing import Any

import pytest

from gaxi.errors import GaxiError
from gaxi.transport import (
    USER_AGENT,
    Headers,
    RecordingTransport,
    Response,
    Transport,
    _NoRedirect,
)


def raw_response(status: int, pairs: list[tuple[str, str]], body: bytes) -> Any:
    message = Message()
    for name, value in pairs:
        message[name] = value

    class Raw:
        headers = message

        def __init__(self) -> None:
            self.status = status
            self._body = io.BytesIO(body)

        def read(self, amt: int = -1) -> bytes:
            return self._body.read(amt)

    return Raw()


class HeadersTest(unittest.TestCase):
    def test_lookup_ignores_case_but_keeps_the_original_name(self) -> None:
        headers = Headers([("Content-Type", "application/json")])
        assert headers.get("content-TYPE") == "application/json"
        assert "CONTENT-TYPE" in headers
        assert headers.items() == [("Content-Type", "application/json")]

    def test_absent_header_returns_the_default(self) -> None:
        headers = Headers()
        assert headers.get("ETag") is None
        assert headers.get("ETag", "none") == "none"
        assert "ETag" not in headers


class ResponseTest(unittest.TestCase):
    def test_media_type_drops_parameters(self) -> None:
        response = Response(200, [("Content-Type", "TEXT/Plain; charset=UTF-8")])
        assert response.media_type == "text/plain"

    def test_charset_is_read_from_the_content_type(self) -> None:
        assert Response(200, [("Content-Type", "text/plain; charset=latin-1")]).charset == "latin-1"
        assert Response(200, [("Content-Type", 'text/plain; charset="utf-16"')]).charset == "utf-16"
        assert Response(200, [("Content-Type", "text/plain; boundary=x")]).charset == "utf-8"
        assert Response(200, []).charset == "utf-8"

    def test_reading_drains_the_stream_once(self) -> None:
        response = Response(200, [], stream=io.BytesIO(b"payload"))
        assert response.read_all() == b"payload"
        assert response.stream is None
        assert response.read_all() == b"payload"


class TransportTest(unittest.TestCase):
    def test_only_http_and_https_are_requested(self) -> None:
        with pytest.raises(GaxiError) as caught:
            Transport().send("GET", "file:///etc/passwd")
        assert "only http and https" in caught.value.message
        with pytest.raises(GaxiError) as caught:
            Transport().send("GET", "gitea.example.com/api")
        assert "a scheme-less URL" in caught.value.message

    def test_a_successful_response_carries_headers_and_body(self) -> None:
        transport = Transport()
        sent: dict[str, Any] = {}

        def opener(request: Any, timeout: int) -> Any:
            sent["request"] = request
            sent["timeout"] = timeout
            return raw_response(200, [("Content-Type", "application/json")], b"{}")

        transport._opener.open = opener  # type: ignore[method-assign, assignment]
        response = transport.send("get", "https://gitea.example.com/x", {"X-Extra": "1"})
        assert response.status == 200
        assert response.body == b"{}"
        assert sent["request"].get_header("User-agent") == USER_AGENT
        assert sent["request"].get_header("X-extra") == "1"
        assert sent["request"].get_method() == "GET"

    def test_a_streamed_response_keeps_the_handle_open(self) -> None:
        transport = Transport()
        def opener(request: Any, timeout: int) -> Any:
            return raw_response(200, [], b"chunk")

        transport._opener.open = opener  # type: ignore[method-assign, assignment]
        response = transport.send("GET", "https://gitea.example.com/x", stream=True)
        assert response.body == b""
        assert response.read_all() == b"chunk"

    def test_an_http_error_is_a_response_not_a_failure(self) -> None:
        transport = Transport()

        def opener(request: Any, timeout: int) -> Any:
            raise urllib.error.HTTPError(
                "https://gitea.example.com/x", 404, "Not Found", Message(), io.BytesIO(b"nope"),
            )

        transport._opener.open = opener  # type: ignore[method-assign, assignment]
        response = transport.send("GET", "https://gitea.example.com/x")
        assert response.status == 404
        assert response.body == b"nope"

    def test_an_unreachable_instance_is_a_structured_failure(self) -> None:
        transport = Transport()

        def opener(request: Any, timeout: int) -> Any:
            raise urllib.error.URLError("name resolution failed")

        transport._opener.open = opener  # type: ignore[method-assign, assignment]
        with pytest.raises(GaxiError) as caught:
            transport.send("GET", "https://gitea.example.com/x")
        assert "cannot reach" in caught.value.message
        assert caught.value.details == [("request", "GET https://gitea.example.com/x")]

    def test_a_protocol_failure_is_structured_too(self) -> None:
        transport = Transport()

        def opener(request: Any, timeout: int) -> Any:
            raise http.client.BadStatusLine("garbage")

        transport._opener.open = opener  # type: ignore[method-assign, assignment]
        with pytest.raises(GaxiError) as caught:
            transport.send("GET", "https://gitea.example.com/x")
        assert "cannot reach" in caught.value.message

    def test_redirects_are_never_followed_by_the_transport(self) -> None:
        assert _NoRedirect().redirect_request(None, None, 302, "", None, "") is None


class RecordingTransportTest(unittest.TestCase):
    def test_running_out_of_scripted_responses_is_a_failure(self) -> None:
        with pytest.raises(GaxiError) as caught:
            RecordingTransport().send("GET", "https://gitea.example.com/x")
        assert "no scripted response" in caught.value.message

    def test_a_streamed_reply_is_wrapped_in_a_handle(self) -> None:
        transport = RecordingTransport([Response(200, [], body=b"payload")])
        response = transport.send("GET", "https://gitea.example.com/x", stream=True)
        assert response.body == b""
        assert response.read_all() == b"payload"
