import unittest

from gaxi.document import Aggregate, Document, Lines, Mapping, Scalar, Table
from gaxi.encode import to_json, to_toon, to_yaml


class EncodeTest(unittest.TestCase):
    def test_collection_shape(self) -> None:
        document = Document()
        document.add("count", Aggregate(2, 17))
        document.add("pull_requests", Table(
            ["index", "title", "state", "updated_at"],
            [[41, "Fix race", "open", "2026-08-29T18:12:00Z"],
             [37, "Update docs", "open", "2026-08-28T09:31:00Z"]]))
        document.add("help", Lines(["gaxi get /repos/acme/widgets/pulls/<index>"]))
        assert to_toon(document) == (
            "count: 2 of 17 total\n"
            "pull_requests[2]{index,title,state,updated_at}:\n"
            "  41,Fix race,open,2026-08-29T18:12:00Z\n"
            "  37,Update docs,open,2026-08-28T09:31:00Z\n"
            "help[1]:\n"
            "  - gaxi get /repos/acme/widgets/pulls/<index>"
        )

    def test_empty_collection_emits_exact_count_zero(self) -> None:
        document = Document()
        document.add("count", Aggregate(0, 0))
        document.add("issues", Table(["index", "title", "state"], []))
        assert to_toon(document) == "count: 0\nissues[0]{index,title,state}:"

    def test_unknown_total_is_named(self) -> None:
        document = Document()
        document.add("count", Aggregate(20, "unknown"))
        document.add("page", Scalar(1))
        assert to_toon(document) == "count: 20\ntotal: unknown\npage: 1"

    def test_unpaginated_collection_is_complete(self) -> None:
        document = Document()
        document.add("count", Aggregate(3))
        assert to_toon(document) == "count: 3 of 3 total"

    def test_detail_object_has_no_count(self) -> None:
        document = Document()
        mapping = Mapping().add("index", Scalar(42)).add("title", Scalar("Broken deployment"))
        document.add("issue", mapping)
        assert to_toon(document) == "issue:\n  index: 42\n  title: Broken deployment"

    def test_row_values_with_commas_are_quoted(self) -> None:
        document = Document()
        document.add("rows", Table(["a"], [["x, y"]]))
        assert '"x, y"' in to_toon(document)

    def test_formats_encode_the_same_logical_result(self) -> None:
        document = Document()
        document.add("count", Aggregate(1, 5))
        document.add("issues", Table(["index"], [[42]]))
        assert to_json(document) == (
            '{\n  "count": 1,\n  "total": 5,\n  "issues": [\n'
            '    {\n      "index": 42\n    }\n  ]\n}'
        )
        assert to_yaml(document) == "count: 1\ntotal: 5\nissues:\n  - index: 42"


if __name__ == "__main__":
    unittest.main()
