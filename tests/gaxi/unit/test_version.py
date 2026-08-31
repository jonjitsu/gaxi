"""The application version comes from the installed project metadata, read lazily."""

import subprocess
import sys
import tomllib
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import override
from unittest.mock import patch

import pytest

import gaxi
from gaxi import _resolve_version

PYPROJECT = Path(__file__).parents[3] / "pyproject.toml"


def project_version() -> str:
    return str(tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"])


class VersionTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        _resolve_version.cache_clear()
        self.addCleanup(_resolve_version.cache_clear)

    def test_the_version_is_the_one_declared_in_the_project_metadata(self) -> None:
        assert gaxi.__version__ == project_version()

    def test_an_uninstalled_source_checkout_reports_an_explicit_unknown_version(self) -> None:
        with patch("importlib.metadata.version", side_effect=PackageNotFoundError):
            assert _resolve_version() == "unknown"

    def test_the_metadata_is_read_once_and_reused(self) -> None:
        with patch("importlib.metadata.version", return_value="9.9.9") as reader:
            assert gaxi.__version__ == "9.9.9"
            assert gaxi.__version__ == "9.9.9"

        assert reader.call_count == 1

    def test_any_other_missing_attribute_is_still_an_attribute_error(self) -> None:
        with pytest.raises(AttributeError):
            _ = gaxi.no_such_attribute


class LazinessTest(unittest.TestCase):
    def test_importing_gaxi_does_not_read_the_package_metadata(self) -> None:
        """Reading it costs ~45ms, so nothing but an actual version request may pay it."""
        loaded = subprocess.run(
            [sys.executable, "-c", "import sys, gaxi; print('importlib.metadata' in sys.modules)"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert loaded.stdout.strip() == "False"
