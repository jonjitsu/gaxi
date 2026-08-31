"""Integration test against a live instance.

The instance's description is fetched at test time; no Swagger snapshot is kept
as a version registry. Set GAXI_TEST_SERVER to run it (CI starts an ephemeral
Gitea instance and sets it).
"""

import os
import unittest
from typing import ClassVar, override

import pytest

from gaxi.catalog import Catalog
from gaxi.config import normalize_origin
from gaxi.discovery import load_catalog
from gaxi.policy import Policy
from gaxi.transport import Transport

SERVER = os.environ.get("GAXI_TEST_SERVER")

REPRESENTATIVE = [
    ("get", "/version"),
    ("get", "/repos/search"),
    ("get", "/repos/acme/widgets/issues"),
    ("get", "/repos/acme/widgets/pulls"),
    ("get", "/repos/acme/widgets/issues/1"),
    ("post", "/repos/acme/widgets/issues"),
    ("delete", "/repos/acme/widgets/issues/comments/1"),
]


pytestmark = pytest.mark.network


@unittest.skipUnless(SERVER, "set GAXI_TEST_SERVER to run the live compatibility test")
class LiveInstanceTest(unittest.TestCase):
    catalog: ClassVar[Catalog]
    policy: ClassVar[Policy]

    @classmethod
    @override
    def setUpClass(cls) -> None:
        origin = normalize_origin(SERVER)
        cls.catalog, _ = load_catalog(origin, Transport(), refresh=True)
        cls.policy = Policy()

    def test_every_advertised_capability_compiles_uniquely(self) -> None:
        keys = [cap.key for cap in self.catalog.capabilities]
        assert len(keys) == len(set(keys))
        assert len(keys) > 100
        unavailable = self.catalog.unavailable()
        assert unavailable == [], [cap.key for cap in unavailable]

    def test_representative_requests_resolve(self) -> None:
        for method, path in REPRESENTATIVE:
            with self.subTest(request=f"{method} {path}"):
                cap, _ = self.catalog.resolve(method, path)
                assert cap.method == method

    def test_every_capability_resolves_semantic_properties(self) -> None:
        for cap in self.catalog.available():
            props = self.policy.resolve(cap)
            assert props.effect in ("read", "mutate")
            assert props.confirmation in ("none", "required", "unknown")
            assert props.retry in ("safe", "unsafe", "unknown")


if __name__ == "__main__":
    unittest.main()
