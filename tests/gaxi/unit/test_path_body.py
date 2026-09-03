import unittest

from gaxi.binding import Binding, _coerce
from gaxi.catalog import Catalog
from gaxi.path_body import apply_path_body_defaults
from tests.gaxi import support
from tests.gaxi.fixtures import DOCUMENT

CATALOG = Catalog.from_document(DOCUMENT, origin=support.ORIGIN)
CAP = CATALOG.by_key["post:/repos/{owner}/{repo}/issues/{index}/dependencies"]
CREATE_ISSUE = CATALOG.by_key["post:/repos/{owner}/{repo}/issues"]


class PathBodyTest(unittest.TestCase):
    def test_non_dict_single_body_is_left_unchanged(self) -> None:
        binding = Binding()
        binding.body = "literal"
        apply_path_body_defaults(
            CAP,
            binding,
            {"owner": "acme", "repo": "widgets", "index": "23"},
            _coerce,
        )
        assert binding.body == "literal"

    def test_missing_path_value_skips_that_property(self) -> None:
        binding = Binding()
        binding.body = {"index": 22}
        apply_path_body_defaults(
            CAP,
            binding,
            {"owner": "acme", "index": "23"},
            _coerce,
        )
        assert binding.body == {"index": 22, "owner": "acme"}

    def test_batch_skips_non_object_elements(self) -> None:
        binding = Binding()
        binding.batch_bodies = [{"index": 22}, "skip-me"]
        apply_path_body_defaults(
            CAP,
            binding,
            {"owner": "acme", "repo": "widgets", "index": "23"},
            _coerce,
        )
        assert binding.batch_bodies == [
            {"index": 22, "owner": "acme", "repo": "widgets"},
            "skip-me",
        ]

    def test_no_eligible_defaults_leave_body_none(self) -> None:
        binding = Binding()
        apply_path_body_defaults(
            CREATE_ISSUE,
            binding,
            {"owner": "acme", "repo": "widgets"},
            _coerce,
        )
        assert binding.body is None


if __name__ == "__main__":
    unittest.main()
