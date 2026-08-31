"""Auth actions: their failures, and the ones that write configuration."""

import io
import stat
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import override

from gaxi import credentials
from gaxi.commands import auth as auth_command
from gaxi.config import Config
from gaxi.errors import EXIT_USAGE
from tests.gaxi import support
from tests.gaxi.support import run_cli

HELPER = "#!/bin/sh\nexit 0\n"


class AuthUsageTest(unittest.TestCase):
    def test_an_unknown_action_lists_the_known_ones(self) -> None:
        code, out, _ = run_cli(["auth", "frobnicate"])
        assert code == EXIT_USAGE
        assert "unknown auth action frobnicate" in out
        assert "allow-insecure" in out

    def test_actions_other_than_list_require_an_origin(self) -> None:
        code, out, _ = run_cli(["auth", "remove"])
        assert code == EXIT_USAGE
        assert "auth remove requires an instance origin" in out

    def test_a_configured_helper_is_used_when_none_is_named(self) -> None:
        config = Config({"servers": {support.ORIGIN: {"credential_helper": ["true"]}}})
        with unittest.mock.patch.object(auth_command, "run_helper", return_value=None) as helper:
            code, out, _ = run_cli(["auth", "remove", support.ORIGIN], config=config)
        assert code == 0
        assert "  outcome: removed" in out
        assert helper.call_args.args[0] == ["true"]

    def test_allow_insecure_applies_only_to_plaintext(self) -> None:
        code, out, _ = run_cli(["auth", "allow-insecure", "https://gitea.example.com"])
        assert code == EXIT_USAGE
        assert "applies only to plaintext HTTP origins" in out


class AuthWriteTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.helper = self.directory / "helper.sh"
        self.helper.write_text(HELPER, encoding="utf-8")
        self.helper.chmod(self.helper.stat().st_mode | stat.S_IEXEC)
        self.config = Config({}, path=self.directory / "config.json")

    def test_allow_insecure_is_recorded_for_the_exact_origin(self) -> None:
        code, out, _ = run_cli(
            ["auth", "allow-insecure", "http://gitea.local"], config=self.config,
        )
        assert code == 0
        assert "  insecure_transport: true" in out
        assert Config.load(self.directory).insecure_transport_allowed("http://gitea.local")

    def test_an_empty_token_is_refused(self) -> None:
        stdin = sys.stdin
        sys.stdin = io.StringIO("   \n")
        try:
            code, out, _ = run_cli(
                ["auth", "add", support.ORIGIN, "--token-stdin", "--helper", str(self.helper)],
                config=self.config,
            )
        finally:
            sys.stdin = stdin
        assert code == EXIT_USAGE
        assert "no token was supplied on stdin" in out


class HelperProcessTest(unittest.TestCase):
    def test_a_missing_helper_is_a_structured_failure(self) -> None:
        with unittest.mock.patch.object(
            subprocess, "run", side_effect=OSError("not found"),
        ):
            code, out, _ = run_cli(
                ["auth", "remove", support.ORIGIN, "--helper", "absent-helper"],
            )
        assert code == 1
        assert "credential helper failed" in out

    def test_a_failing_store_is_reported_but_a_failing_get_is_not(self) -> None:
        failure = subprocess.CompletedProcess(["helper"], 3, "", "")
        with unittest.mock.patch.object(subprocess, "run", return_value=failure):
            assert credentials.run_helper(["helper"], "get", support.ORIGIN) is None
            code, out, _ = run_cli(
                ["auth", "remove", support.ORIGIN, "--helper", "helper"],
            )
        assert code == 1
        assert "credential helper exited 3" in out


class RedactionTest(unittest.TestCase):
    def test_empty_text_is_returned_untouched(self) -> None:
        assert credentials.redact("", ["secret"]) == ""

    def test_absent_secrets_are_skipped(self) -> None:
        assert credentials.redact("plain", [None, ""]) == "plain"
