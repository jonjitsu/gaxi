"""Configuration locations, origin normalization, and overlays."""

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import override

import pytest

from gaxi.config import Config, cache_home, config_home, load_repo_overlay, normalize_origin
from gaxi.errors import GaxiError


class LocationTest(unittest.TestCase):
    def test_explicit_homes_win_over_xdg(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ", {"GAXI_CONFIG_HOME": "/c", "GAXI_CACHE_HOME": "/k"}, clear=True,
        ):
            assert config_home() == Path("/c")
            assert cache_home() == Path("/k")

    def test_xdg_homes_are_honoured(self) -> None:
        with unittest.mock.patch.dict(
            "os.environ", {"XDG_CONFIG_HOME": "/x", "XDG_CACHE_HOME": "/y"}, clear=True,
        ):
            assert config_home() == Path("/x/gaxi")
            assert cache_home() == Path("/y/gaxi")

    def test_the_home_directory_is_the_fallback(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True):
            assert config_home() == Path.home() / ".config" / "gaxi"
            assert cache_home() == Path.home() / ".cache" / "gaxi"


class OriginTest(unittest.TestCase):
    def test_a_bare_host_is_assumed_to_be_https(self) -> None:
        assert normalize_origin("gitea.example.com") == "https://gitea.example.com"

    def test_an_empty_origin_is_rejected(self) -> None:
        with pytest.raises(GaxiError) as caught:
            normalize_origin("")
        assert "an instance origin is required" in caught.value.message

    def test_an_unsupported_scheme_is_rejected(self) -> None:
        with pytest.raises(GaxiError) as caught:
            normalize_origin("ftp://gitea.example.com")
        assert "unsupported instance scheme" in caught.value.message

    def test_an_origin_without_a_host_is_rejected(self) -> None:
        with pytest.raises(GaxiError) as caught:
            normalize_origin("https:///path")
        assert "has no host" in caught.value.message


class ConfigFileTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())

    def test_an_absent_file_loads_as_empty(self) -> None:
        config = Config.load(self.directory)
        assert config.data == {}
        assert config.path == self.directory / "config.json"

    def test_a_saved_file_round_trips(self) -> None:
        config = Config.load(self.directory)
        config.set_server("https://gitea.example.com", {"credential_helper": ["helper"]})
        config.save()
        assert Config.load(self.directory).servers() == {
            "https://gitea.example.com": {"credential_helper": ["helper"]},
        }

    def test_unreadable_configuration_is_a_structured_failure(self) -> None:
        (self.directory / "config.json").write_text("{ not json", encoding="utf-8")
        with pytest.raises(GaxiError) as caught:
            Config.load(self.directory)
        assert "cannot read configuration" in caught.value.message

    def test_the_default_path_is_the_config_home(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"GAXI_CONFIG_HOME": str(self.directory)}):
            assert Config().path == self.directory / "config.json"

    def test_default_server_is_normalized_and_optional(self) -> None:
        assert Config({}).default_server is None
        assert Config({"default_server": "gitea.example.com"}).default_server == (
            "https://gitea.example.com")

    def test_a_string_credential_helper_becomes_one_argument(self) -> None:
        config = Config({"servers": {"o": {"credential_helper": "helper"}}})
        assert config.credential_helper("o") == ["helper"]
        assert config.credential_helper("absent") is None

    def test_ssh_hosts_map_case_insensitively(self) -> None:
        config = Config({"servers": {"https://o": {"ssh_hosts": ["Gitea.Example.com"]}}})
        assert config.ssh_origin("gitea.example.com") == "https://o"
        assert config.ssh_origin("other.example.com") is None

    def test_insecure_transport_is_opt_in(self) -> None:
        assert Config({}).insecure_transport_allowed("http://o") is False
        allowed = Config({"servers": {"http://o": {"insecure_transport": True}}})
        assert allowed.insecure_transport_allowed("http://o") is True


class RepositoryOverlayTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp())

    def test_no_root_and_no_file_both_mean_no_overlay(self) -> None:
        assert load_repo_overlay(None) == {}
        assert load_repo_overlay(self.root) == {}

    def test_an_overlay_is_read_from_the_repository(self) -> None:
        (self.root / ".gaxi").mkdir()
        payload = {"entities": {"PullRequest": {"entity": "prs"}}}
        (self.root / ".gaxi" / "overlay.json").write_text(json.dumps(payload), encoding="utf-8")
        assert load_repo_overlay(self.root) == payload

    def test_an_unreadable_overlay_is_a_structured_failure(self) -> None:
        (self.root / ".gaxi").mkdir()
        (self.root / ".gaxi" / "overlay.json").write_text("{ not json", encoding="utf-8")
        with pytest.raises(GaxiError) as caught:
            load_repo_overlay(self.root)
        assert "cannot read repository overlay" in caught.value.message
