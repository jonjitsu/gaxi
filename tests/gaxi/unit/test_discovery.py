import json
import os
import tempfile
import unittest
from collections.abc import Mapping
from typing import override

import pytest

from gaxi.config import Config, normalize_origin
from gaxi.discovery import load_catalog, resolve_origin
from gaxi.errors import GaxiError
from gaxi.repo_context import RepositoryContext, parse_remote
from gaxi.transport import RecordingTransport, Response
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT


def html(body: str, url: str = "https://gitea.example.com/api/swagger") -> Response:
    return Response(200, [("Content-Type", "text/html")], body.encode("utf-8"), url=url)


def swagger(headers: Mapping[str, str] | None = None) -> Response:
    pairs = [("Content-Type", "application/json"), *list((headers or {}).items())]
    return Response(200, pairs, json.dumps(DOCUMENT).encode("utf-8"))


class OriginTest(unittest.TestCase):
    def test_normalization_drops_default_ports_and_user_information(self) -> None:
        assert normalize_origin("HTTPS://User@Gitea.Example.com:443/") == (
            "https://gitea.example.com")
        assert normalize_origin("https://gitea.example.com:8443/gitea/") == (
            "https://gitea.example.com:8443/gitea")

    def test_http_remote_supplies_owner_and_repository(self) -> None:
        remote = parse_remote("origin", "https://gitea.home.arpa/acme/widgets.git")
        assert (remote.origin, remote.owner, remote.repo) == (
            "https://gitea.home.arpa", "acme", "widgets")

    def test_ssh_remote_is_not_downgraded_to_http(self) -> None:
        remote = parse_remote("origin", "git@gitea.home.arpa:acme/widgets.git")
        assert (remote.scheme, remote.host, remote.full_name) == (
            "ssh", "gitea.home.arpa", "acme/widgets")
        origin, _ = resolve_origin(
            Config({}), RepositoryContext("/repo", "master", [remote]), env={},
        )
        assert origin == "https://gitea.home.arpa"

    def test_saved_mapping_supplies_a_custom_port(self) -> None:
        config = Config({"servers": {"https://gitea.home.arpa:8443/gitea": {
            "ssh_hosts": ["gitea.home.arpa"]}}})
        remote = parse_remote("origin", "git@gitea.home.arpa:acme/widgets.git")
        origin, source = resolve_origin(
            config, RepositoryContext("/repo", "master", [remote]), env={},
        )
        assert origin == "https://gitea.home.arpa:8443/gitea"
        assert source == "repository remote origin"

    def test_selection_order(self) -> None:
        config = Config({"default_server": "https://configured.example.com"})
        repository = RepositoryContext("/repo", "master", [
            parse_remote("origin", support.REMOTE)])
        flagged = resolve_origin(config, repository, server_option="https://flag.example.com")
        assert flagged[0] == "https://flag.example.com"
        from_env = resolve_origin(config, repository, env={"GITEA_SERVER": "https://env.example.com"})
        assert from_env[0] == "https://env.example.com"
        assert resolve_origin(config, repository, env={})[0] == support.ORIGIN
        assert resolve_origin(config, RepositoryContext(), env={})[0] == "https://configured.example.com"

    def test_sole_unambiguous_remote_when_origin_is_absent(self) -> None:
        repository = RepositoryContext("/repo", "master", [
            parse_remote("upstream", "https://gitea.example.com/acme/widgets.git")])
        origin, source = resolve_origin(Config({}), repository, env={})
        assert origin == support.ORIGIN
        assert source == "repository remote upstream"

    def test_no_instance_is_a_structured_setup_failure(self) -> None:
        with pytest.raises(GaxiError) as caught:
            resolve_origin(Config({}), RepositoryContext(), env={})
        assert "no Gitea instance" in caught.value.message
        assert caught.value.help_commands


class CatalogFetchTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp()

    def test_discovery_page_points_at_the_description(self) -> None:
        logged: list[tuple[str, str]] = []
        transport = RecordingTransport([
            html('<div id="swagger-ui" data-source="/swagger.v1.json"></div>'),
            swagger({"ETag": '"v1"'}),
        ])
        catalog, requests = load_catalog(
            support.ORIGIN,
            transport,
            self.directory,
            log_request=lambda method, url: logged.append((method, url)),
        )
        assert requests == 2
        assert logged == [
            ("GET", "https://gitea.example.com/api/swagger"),
            ("GET", "https://gitea.example.com/swagger.v1.json"),
        ]
        assert transport.requests[1]["url"] == "https://gitea.example.com/swagger.v1.json"
        assert catalog.base_path == "/api/v1"
        assert catalog.server_version == "1.27.2"

    def test_warm_cache_sends_no_request(self) -> None:
        transport = RecordingTransport([
            html('<div data-source="/swagger.v1.json"></div>'), swagger()])
        load_catalog(support.ORIGIN, transport, self.directory)
        catalog, requests = load_catalog(support.ORIGIN, transport, self.directory)
        assert requests == 0
        assert catalog.available()

    def test_stale_cache_revalidates_conditionally(self) -> None:
        transport = RecordingTransport([
            html('<div data-source="/swagger.v1.json"></div>'), swagger({"ETag": '"v1"'})])
        load_catalog(support.ORIGIN, transport, self.directory)
        os.environ["GAXI_CACHE_TTL"] = "0"
        try:
            transport.responses.append(Response(304, [("Content-Type", "application/json")]))
            catalog, requests = load_catalog(support.ORIGIN, transport, self.directory)
        finally:
            del os.environ["GAXI_CACHE_TTL"]
        assert requests == 1
        assert transport.requests[-1]["headers"]["If-None-Match"] == '"v1"'
        assert catalog.available()

    def test_unsupported_description_version_fails_structurally(self) -> None:
        document = json.dumps({"openapi": "3.1.0", "paths": {}, "swagger": "3.0"})
        transport = RecordingTransport([
            html('<div data-source="/swagger.v1.json"></div>'),
            Response(200, [("Content-Type", "application/json")], document.encode()),
        ])
        with pytest.raises(GaxiError) as caught:
            load_catalog("https://other.example.com", transport, self.directory)
        assert "unsupported description version" in caught.value.message


if __name__ == "__main__":
    unittest.main()
