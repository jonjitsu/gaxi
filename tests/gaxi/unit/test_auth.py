import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import override

from gaxi.config import Config
from tests.gaxi import support
from tests.gaxi.support import run_cli

HELPER = """#!/bin/sh
action="$1"; origin="$2"; store="$GAXI_TEST_STORE"
case "$action" in
  store) cat > "$store.$(echo "$origin" | tr -c 'a-zA-Z0-9' '_')" ;;
  get) cat "$store.$(echo "$origin" | tr -c 'a-zA-Z0-9' '_')" 2>/dev/null || exit 1 ;;
  erase) rm -f "$store.$(echo "$origin" | tr -c 'a-zA-Z0-9' '_')" ;;
esac
"""


class AuthTest(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.directory = Path(tempfile.mkdtemp())
        self.helper = self.directory / "helper.sh"
        self.helper.write_text(HELPER, encoding="utf-8")
        self.helper.chmod(self.helper.stat().st_mode | stat.S_IEXEC)
        os.environ["GAXI_TEST_STORE"] = str(self.directory / "store")
        self.config = Config({}, path=self.directory / "config.json")

    @override
    def tearDown(self) -> None:
        os.environ.pop("GAXI_TEST_STORE", None)

    def test_tokens_are_never_accepted_as_arguments(self) -> None:
        code, out, _ = run_cli(["auth", "add", support.ORIGIN], config=self.config)
        assert code == 2
        assert "--token-stdin" in out

    def test_add_without_a_helper_refuses_to_store_plaintext(self) -> None:
        stdin, sys.stdin = sys.stdin, io.StringIO("secret\n")
        try:
            code, out, _ = run_cli(["auth", "add", support.ORIGIN, "--token-stdin"],
                                   config=self.config)
        finally:
            sys.stdin = stdin
        assert code == 1
        assert "no credential helper is configured" in out

    def test_stored_credential_is_read_back_through_the_helper(self) -> None:
        stdin, sys.stdin = sys.stdin, io.StringIO("secret-token\n")
        try:
            code, out, _ = run_cli(["auth", "add", support.ORIGIN, "--token-stdin",
                                    "--helper", str(self.helper)], config=self.config)
        finally:
            sys.stdin = stdin
        assert code == 0
        assert "  outcome: stored" in out
        assert "secret-token" not in out

        assert "secret-token" not in self.config.path.read_text(encoding="utf-8")

        code, _, session = run_cli(["get", "/user"], config=Config.load(self.directory),
                                   responses=[support.json_response({"login": "alice"})])
        assert code == 0
        assert support.recorded(session)[0]["headers"]["Authorization"] == "token secret-token"

    def test_auth_list_never_prints_token_material(self) -> None:
        self.config.set_server(support.ORIGIN, {"credential_helper": [str(self.helper)]})
        code, out, _ = run_cli(["auth", "list"], config=self.config,
                               env={"GITEA_SERVER": support.ORIGIN,
                                    "GITEA_TOKEN": "secret-token"})
        assert code == 0
        assert "credentials[2]{origin,source,helper,insecure_transport}:" in out
        assert "secret-token" not in out

    def test_no_help_omits_suggestions_from_auth_list(self) -> None:
        self.config.set_server(support.ORIGIN, {"credential_helper": [str(self.helper)]})
        code, out, _ = run_cli(["auth", "list", "--no-help"], config=self.config)
        assert code == 0
        assert "credentials[" in out
        assert "help[" not in out


if __name__ == "__main__":
    unittest.main()
