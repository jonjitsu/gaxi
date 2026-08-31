"""Description discovery, conditional caching, and description validation."""

import json
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path
from typing import override

import pytest

from gaxi import discovery
from gaxi.discovery import load_catalog
from gaxi.errors import GaxiError
from gaxi.transport import RecordingTransport, Response
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT

ORIGIN = support.ORIGIN


def swagger(headers: dict[str, str] | None = None) -> Response:
    pairs = [("Content-Type", "application/json"), *list((headers or {}).items())]
    return Response(200, pairs, json.dumps(DOCUMENT).encode("utf-8"))


class CacheTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.cache = Path(tempfile.mkdtemp())

    def test_a_fresh_cache_is_used_without_a_request(self) -> None:
        transport = RecordingTransport([swagger(), swagger()])
        load_catalog(ORIGIN, transport, self.cache)
        second = RecordingTransport([])
        catalog, requests = load_catalog(ORIGIN, second, self.cache)
        assert requests == 0
        assert catalog.available()
        assert second.requests == []

    def test_a_stale_cache_is_revalidated_and_may_be_unchanged(self) -> None:
        stored = swagger({"ETag": "v1", "Last-Modified": "yesterday"})
        transport = RecordingTransport([swagger(), stored])
        load_catalog(ORIGIN, transport, self.cache)
        with unittest.mock.patch.object(time, "time", return_value=time.time() + 10_000):
            revalidating = RecordingTransport([Response(304, [])])
            catalog, requests = load_catalog(ORIGIN, revalidating, self.cache)
        assert requests == 1
        assert catalog.available()
        sent = revalidating.requests[0]["headers"]
        assert sent["If-None-Match"] == "v1"
        assert sent["If-Modified-Since"] == "yesterday"

    def test_a_stale_cache_accepts_a_replacement_document(self) -> None:
        transport = RecordingTransport([swagger(), swagger({"ETag": "v1"})])
        load_catalog(ORIGIN, transport, self.cache)
        with unittest.mock.patch.object(time, "time", return_value=time.time() + 10_000):
            replacing = RecordingTransport([swagger()])
            catalog, requests = load_catalog(ORIGIN, replacing, self.cache)
        assert requests == 1
        assert catalog.available()

    def test_a_failed_revalidation_falls_back_to_rediscovery(self) -> None:
        transport = RecordingTransport([swagger(), swagger({"ETag": "v1"})])
        load_catalog(ORIGIN, transport, self.cache)
        with unittest.mock.patch.object(time, "time", return_value=time.time() + 10_000):
            failing = RecordingTransport([Response(500, []), swagger(), swagger()])
            catalog, requests = load_catalog(ORIGIN, failing, self.cache)
        assert requests == 3
        assert catalog.available()

    def test_refresh_ignores_the_cache_entirely(self) -> None:
        load_catalog(ORIGIN, RecordingTransport([swagger(), swagger()]), self.cache)
        transport = RecordingTransport([swagger(), swagger()])
        _, requests = load_catalog(ORIGIN, transport, self.cache, refresh=True)
        assert requests == 2

    def test_an_unwritable_cache_directory_is_not_fatal(self) -> None:
        with unittest.mock.patch.object(Path, "mkdir", side_effect=OSError("read-only")):
            catalog, _ = load_catalog(
                ORIGIN, RecordingTransport([swagger(), swagger()]), self.cache,
            )
        assert catalog.available()

    def test_an_unreadable_ttl_falls_back_to_the_default(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"GAXI_CACHE_TTL": "soon"}):
            assert discovery._ttl() == discovery.DEFAULT_TTL
        with unittest.mock.patch.dict("os.environ", {"GAXI_CACHE_TTL": "5"}):
            assert discovery._ttl() == 5


class DocumentTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.cache = Path(tempfile.mkdtemp())

    def test_a_failed_description_request_is_structured(self) -> None:
        transport = RecordingTransport([Response(404, []), Response(404, [])])
        with pytest.raises(GaxiError) as caught:
            load_catalog(ORIGIN, transport, self.cache)
        assert "instance description request failed with status 404" in caught.value.message

    def test_a_non_json_description_is_rejected(self) -> None:
        broken = Response(200, [("Content-Type", "application/json")], b"{ not json")
        with pytest.raises(GaxiError) as caught:
            load_catalog(ORIGIN, RecordingTransport([broken, broken]), self.cache)
        assert "instance description is not valid JSON" in caught.value.message

    def test_a_description_without_paths_is_rejected(self) -> None:
        empty = Response(200, [("Content-Type", "application/json")], b'{"swagger": "2.0"}')
        with pytest.raises(GaxiError) as caught:
            load_catalog(ORIGIN, RecordingTransport([empty, empty]), self.cache)
        assert "declares no paths" in caught.value.message


class DiscoveryPageTest(unittest.TestCase):
    def test_a_json_discovery_page_is_the_description(self) -> None:
        transport = RecordingTransport([swagger(), swagger()])
        url, requests = discovery._discover_document_url(ORIGIN, transport)
        assert url == ORIGIN + discovery.DISCOVERY_PATH
        assert requests == 1

    def test_a_page_without_a_data_source_falls_back(self) -> None:
        page = Response(200, [("Content-Type", "text/html")], b"<html></html>")
        url, _ = discovery._discover_document_url(ORIGIN, RecordingTransport([page]))
        assert url == ORIGIN + discovery.FALLBACK_DOCUMENT
