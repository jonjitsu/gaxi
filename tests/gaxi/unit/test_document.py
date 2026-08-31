"""Logical documents and the naming of the executable."""

import sys
import unittest
import unittest.mock
from pathlib import Path

from gaxi import naming
from gaxi.document import Aggregate, Document, Lines, Mapping, Node, Scalar, Table
from gaxi.helpdoc import root_help


class DocumentTest(unittest.TestCase):
    def test_bare_values_are_wrapped_as_scalars(self) -> None:
        document = Document().add("count", 3)
        node = document.get("count")
        assert isinstance(node, Scalar)
        assert node.value == 3

    def test_keys_are_reported_in_order(self) -> None:
        document = Document().add("a", 1).add("b", 2)
        assert document.keys() == ["a", "b"]

    def test_an_absent_key_resolves_to_nothing(self) -> None:
        assert Document().get("absent") is None

    def test_a_mapping_nests_nodes_and_bare_values(self) -> None:
        mapping = Mapping().add("child", Scalar("x")).add("plain", 1)
        assert [key for key, _ in mapping.pairs] == ["child", "plain"]
        assert all(isinstance(node, Node) for _, node in mapping.pairs)

    def test_tables_and_lines_copy_their_input(self) -> None:
        rows = [[1, 2]]
        table = Table(["a", "b"], rows)
        rows.append([3, 4])
        assert table.rows == [[1, 2]]
        assert Lines(iter(["one"])).items == ["one"]

    def test_an_aggregate_carries_the_server_total(self) -> None:
        assert Aggregate(2, 17).total == 17
        assert Aggregate(2).total is None


class ExecutableNameTest(unittest.TestCase):
    def test_the_environment_pins_the_name(self) -> None:
        with unittest.mock.patch.dict("os.environ", {"GAXI_EXECUTABLE_NAME": "bridge"}):
            assert naming.executable() == "bridge"

    def test_a_script_path_falls_back_to_the_default(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True), \
             unittest.mock.patch.object(sys, "argv", ["/usr/lib/run.py"]):
            assert naming.executable() == naming.DEFAULT_NAME

    def test_an_installed_name_is_used_as_typed(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True), \
             unittest.mock.patch.object(sys, "argv", ["/usr/bin/gaxi"]):
            assert naming.executable() == "gaxi"
            assert naming.executable_path() == "/usr/bin/gaxi"

    def test_a_path_under_the_home_directory_is_abbreviated(self) -> None:
        target = str(Path.home() / "bin" / "gaxi")
        with unittest.mock.patch.dict("os.environ", {}, clear=True), \
             unittest.mock.patch.object(sys, "argv", [target]):
            assert naming.executable_path() == "~/bin/gaxi"

    def test_an_unrecognisable_program_reports_only_the_default(self) -> None:
        with unittest.mock.patch.dict("os.environ", {}, clear=True), \
             unittest.mock.patch.object(sys, "argv", ["/usr/lib/run.py"]):
            assert naming.executable_path() == naming.DEFAULT_NAME

    def test_values_are_quoted_only_when_they_need_it(self) -> None:
        assert naming.quote("open") == "open"
        assert naming.quote("two words") == '"two words"'
        assert naming.quote("") == '""'
        assert naming.quote('say "hi"') == '"say \\"hi\\""'

    def test_a_command_carries_assignments_and_options(self) -> None:
        rendered = naming.command("get", "/x", [("state", "open")], ["--full"])
        assert rendered.endswith("get /x state=open --full")


class RootHelpTest(unittest.TestCase):
    def test_the_root_help_lists_every_command(self) -> None:
        document = root_help()
        assert document.keys() == ["gaxi", "commands", "options", "help"]
        commands = document.get("commands")
        assert isinstance(commands, Table)
        assert ["capabilities"] in [row[:1] for row in commands.rows]
