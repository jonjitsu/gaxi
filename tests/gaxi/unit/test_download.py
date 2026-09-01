"""Download a response body to disk."""

import hashlib
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import pytest

from gaxi.download import Receipt, save
from gaxi.errors import GaxiError
from gaxi.transport import Response


class SaveTest(unittest.TestCase):
    def test_a_body_already_in_memory_is_written_in_one_go(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "out.bin")
            receipt = save(Response(200, [], body=b"payload"), path)
            assert receipt == Receipt(
                path=path,
                size=len(b"payload"),
                media_type="application/octet-stream",
                sha256=hashlib.sha256(b"payload").hexdigest(),
            )
            assert Path(path).read_bytes() == b"payload"

    def test_a_streamed_body_is_hashed_while_it_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "out.bin")
            payload = b"x" * 200_000
            receipt = save(
                Response(200, [("Content-Type", "application/zip")], body=payload),
                path,
            )
            assert receipt.size == len(payload)
            assert receipt.media_type == "application/zip"
            assert Path(path).read_bytes() == payload
            assert receipt.sha256 == hashlib.sha256(payload).hexdigest()

    def test_an_existing_destination_fails_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "out.bin")
            Path(path).write_bytes(b"old")
            with pytest.raises(GaxiError, match="already exists"):
                save(Response(200, [], body=b"new"), path)
            assert Path(path).read_bytes() == b"old"

    def test_overwrite_replaces_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "out.bin")
            Path(path).write_bytes(b"old")
            save(Response(200, [], body=b"new"), path, overwrite=True)
            assert Path(path).read_bytes() == b"new"

    def test_an_unwritable_destination_is_a_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "out.bin")
            with (
                unittest.mock.patch.object(Path, "open", side_effect=OSError("read-only")),
                pytest.raises(GaxiError, match="cannot save response"),
            ):
                save(Response(200, [], body=b"x"), path)
