import unittest
from collections.abc import Mapping
from typing import ClassVar

import pytest

from gaxi.config import Config
from gaxi.credentials import CredentialResolver, redact
from gaxi.errors import GaxiError
from gaxi.transport import Response
from tests.gaxi import support
from tests.gaxi.support import json_response, response, run_cli

OTHER = "https://other.example.com"


class ResolverTest(unittest.TestCase):
    def resolver(
        self,
        env: Mapping[str, str],
        config: Config | None = None,
    ) -> CredentialResolver:
        return CredentialResolver(config or Config({}), env)

    def test_environment_pair_binds_to_its_origin(self) -> None:
        credential = self.resolver({"GITEA_SERVER": support.ORIGIN,
                                    "GITEA_TOKEN": "secret"}).resolve(support.ORIGIN)
        assert credential is not None
        assert credential.source == "environment"
        assert credential.headers() == {"Authorization": "token secret"}

    def test_token_without_server_is_an_error(self) -> None:
        with pytest.raises(GaxiError) as caught:
            self.resolver({"GITEA_TOKEN": "secret"}).resolve(support.ORIGIN)
        assert "without GITEA_SERVER" in caught.value.message

    def test_mismatched_origin_fails_rather_than_leaking(self) -> None:
        with pytest.raises(GaxiError) as caught:
            self.resolver({"GITEA_SERVER": OTHER, "GITEA_TOKEN": "secret"}).resolve(support.ORIGIN)
        assert "bound to a different origin" in caught.value.message

    def test_anonymous_execution_is_explicit(self) -> None:
        credential = self.resolver({"GITEA_SERVER": OTHER, "GITEA_TOKEN": "secret"}).resolve(
            support.ORIGIN, anonymous=True)
        assert credential is None

    def test_absent_credential_proceeds_anonymously(self) -> None:
        assert self.resolver({}).resolve(support.ORIGIN) is None

    def test_plaintext_transport_requires_an_explicit_setting(self) -> None:
        resolver = self.resolver({"GITEA_SERVER": "http://gitea.local",
                                  "GITEA_TOKEN": "secret"})
        credential = resolver.resolve("http://gitea.local")
        with pytest.raises(GaxiError) as caught:
            resolver.check_transport("http://gitea.local", credential)
        assert "plaintext HTTP" in caught.value.message
        allowed = CredentialResolver(
            Config({"servers": {"http://gitea.local": {"insecure_transport": True}}}),
            {"GITEA_SERVER": "http://gitea.local", "GITEA_TOKEN": "secret"})
        allowed.check_transport("http://gitea.local", credential)

    def test_redaction_replaces_every_occurrence(self) -> None:
        assert redact("token abc and abc", ["abc"]) == "token <redacted> and <redacted>"


class RequestCredentialTest(unittest.TestCase):
    ENV: ClassVar[dict[str, str]] = {
        "GITEA_SERVER": support.ORIGIN,
        "GITEA_TOKEN": "secret-token",
    }

    def test_matching_credential_is_attached(self) -> None:
        _, _, session = run_cli(["get", "/user"], env=self.ENV,
                                responses=[json_response({"login": "alice"})])
        assert support.recorded(session)[0]["headers"]["Authorization"] == "token secret-token"

    def test_anonymous_sends_no_credential(self) -> None:
        _, _, session = run_cli(["get", "/user", "--anonymous"], env=self.ENV,
                                responses=[json_response({"login": "alice"})])
        assert "Authorization" not in support.recorded(session)[0]["headers"]

    def test_credentials_never_appear_in_output(self) -> None:
        code, out, _ = run_cli(["get", "/user", "--dry-run"], env=self.ENV)
        assert code == 0
        assert "  credential: environment" in out
        assert "secret-token" not in out

    def test_api_returned_secrets_remain_response_data(self) -> None:
        payload = {"id": 3, "name": "ci", "sha1": "1234567890abcdef", "scopes": ["write"]}
        code, out, _ = run_cli(["get", "/user", "--fields", "id,sha1"], env=self.ENV,
                               responses=[json_response(payload)])
        assert code == 0
        assert "  sha1: 1234567890abcdef" in out

    def test_failures_still_redact_the_credential(self) -> None:
        failure = json_response({"message": "token secret-token is invalid"}, status=401)
        code, out, _ = run_cli(["get", "/user"], env=self.ENV, responses=[failure])
        assert code == 1
        assert "secret-token" not in out
        assert "<redacted>" in out


class RedirectTest(unittest.TestCase):
    def test_get_redirects_are_followed_within_the_origin(self) -> None:
        redirect = response(302, b"", headers={
            "Location": support.ORIGIN + "/api/v1/repos/acme/widgets/pulls/1"})
        code, _out, session = run_cli(
            ["get", "/repos/acme/widgets/redirect"], env=RequestCredentialTest.ENV,
            responses=[redirect, json_response({"index": 1, "title": "t", "state": "open",
                                                "updated_at": "u"})])
        assert code == 0
        assert len(support.recorded(session)) == 2
        assert "Authorization" in support.recorded(session)[1]["headers"]

    def test_credentials_are_dropped_when_the_origin_changes(self) -> None:
        redirect = response(302, b"", headers={"Location": OTHER + "/elsewhere"})
        code, _, session = run_cli(
            ["get", "/repos/acme/widgets/redirect"], env=RequestCredentialTest.ENV,
            responses=[redirect, json_response({"index": 1, "title": "t", "state": "open",
                                                "updated_at": "u"})])
        assert code == 0
        assert "Authorization" not in support.recorded(session)[1]["headers"]

    def test_mutation_redirects_are_refused(self) -> None:
        redirect = response(302, b"", headers={"Location": OTHER + "/elsewhere"})
        code, out, session = run_cli(
            ["post", "/repos/acme/widgets/issues", "title=x"], responses=[redirect])
        assert code == 1
        assert "refusing to follow a redirect for a mutation" in out
        assert len(support.recorded(session)) == 1

    def test_redirects_are_bounded(self) -> None:
        def hop() -> Response:
            return response(302, b"", headers={
                "Location": support.ORIGIN + "/api/v1/repos/acme/widgets/redirect"})
        code, out, session = run_cli(["get", "/repos/acme/widgets/redirect"],
                                     responses=[hop() for _ in range(8)])
        assert code == 1
        assert "redirect limit of 5 exceeded" in out
        assert len(support.recorded(session)) == 6


if __name__ == "__main__":
    unittest.main()
