"""The home view reports live state, and names what it could not determine."""

import unittest

from gaxi.options import DiscoveryOptions, Options
from tests.gaxi import support
from tests.gaxi.support import json_response, response, run_cli

ENV = {"GITEA_SERVER": support.ORIGIN, "GITEA_TOKEN": "secret-token"}


class IdentityTest(unittest.TestCase):
    def test_a_verified_credential_reports_the_login(self) -> None:
        code, out, _ = run_cli(
            [],
            env=ENV,
            responses=[
                json_response({"login": "alice"}),
                json_response([], headers={"X-Total-Count": "4"}),
                json_response([], headers={"X-Total-Count": "2"}),
            ],
        )
        assert code == 0
        assert "  identity: alice" in out
        assert "  open_issues: 4" in out
        assert "  open_pulls: 2" in out

    def test_an_unverifiable_credential_says_so(self) -> None:
        code, out, _ = run_cli(
            [],
            env=ENV,
            responses=[
                json_response({"message": "nope"}, status=401),
                json_response([]),
                json_response([]),
            ],
        )
        assert code == 0
        assert "identity: credential from environment (unverified)" in out

    def test_a_non_json_identity_response_is_not_trusted(self) -> None:
        code, out, _ = run_cli(
            [],
            env=ENV,
            responses=[
                response(200, b"<html>", media_type="text/html"),
                json_response([]),
                json_response([]),
            ],
        )
        assert code == 0
        assert "identity: credential from environment (unverified)" in out

    def test_an_identity_payload_without_login_is_not_trusted(self) -> None:
        code, out, _ = run_cli(
            [],
            env=ENV,
            responses=[
                json_response({"id": 1}),
                json_response([], headers={"X-Total-Count": "4"}),
                json_response([], headers={"X-Total-Count": "2"}),
            ],
        )
        assert code == 0
        assert "identity: credential from environment (unverified)" in out

    def test_an_unreachable_identity_endpoint_still_names_the_source(self) -> None:
        code, out, _ = run_cli([], env=ENV, responses=[])
        assert code == 0
        assert "identity: credential from environment" in out


class OpenTotalTest(unittest.TestCase):
    def test_open_issues_request_includes_type_qualifier(self) -> None:
        session = support.make_session(
            options=Options(discovery=DiscoveryOptions(anonymous=True)),
            responses=[
                json_response([], headers={"X-Total-Count": "13"}),
                json_response([], headers={"X-Total-Count": "2"}),
            ],
        )
        code, out, session = run_cli([], session=session)
        assert code == 0
        requests = support.recorded(session)
        assert len(requests) == 2
        assert "type=issues" in requests[0]["url"]
        assert "type=issues" not in requests[1]["url"]
        assert "  open_issues: 13" in out
        assert "  open_pulls: 2" in out

    def test_a_missing_total_falls_back_to_the_returned_length(self) -> None:
        code, out, _ = run_cli(
            [],
            options=Options(discovery=DiscoveryOptions(anonymous=True)),
            responses=[json_response([{"index": 1}]), json_response([])],
        )
        assert code == 0
        assert "  open_issues: 1" in out
        assert "  open_pulls: 0" in out

    def test_an_unparsable_total_is_named_unknown(self) -> None:
        code, out, _ = run_cli(
            [],
            options=Options(discovery=DiscoveryOptions(anonymous=True)),
            responses=[
                json_response([], headers={"X-Total-Count": "many"}),
                response(200, b"<html>", media_type="text/html"),
            ],
        )
        assert code == 0
        assert out.count("unknown") >= 2

    def test_a_failed_aggregate_is_named_unknown(self) -> None:
        code, out, _ = run_cli(
            [],
            options=Options(discovery=DiscoveryOptions(anonymous=True)),
            responses=[json_response({"message": "no"}, status=500)],
        )
        assert code == 0
        assert "  open_issues: unknown" in out
        assert "  open_pulls: unknown" in out
