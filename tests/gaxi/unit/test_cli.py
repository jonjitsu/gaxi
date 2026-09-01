"""Golden output contracts for the command surface."""

import json
import tempfile
import unittest
from pathlib import Path

from gaxi.repo_context import RepositoryContext
from tests.gaxi import support
from tests.gaxi.support import json_response, response, run_cli

PULLS = [
    {"number": 41, "title": "Fix race", "state": "open",
     "updated_at": "2026-08-29T18:12:00Z", "body": "b"},
    {"number": 37, "title": "Update docs", "state": "open",
     "updated_at": "2026-08-28T09:31:00Z", "body": "b"},
]


class CollectionTest(unittest.TestCase):
    def test_aggregate_precedes_a_named_typed_table(self) -> None:
        code, out, session = run_cli(
            ["get", "/repos/acme/widgets/pulls", "state=open"],
            responses=[json_response(PULLS, headers={"X-Total-Count": "17"})])
        assert code == 0
        assert out.splitlines()[:5] == [
            "count: 2 of 17 total",
            "page: 1",
            "pull_requests[2]{number,title,state,updated_at}:",
            "  41,Fix race,open,2026-08-29T18:12:00Z",
            "  37,Update docs,open,2026-08-28T09:31:00Z",
        ]
        assert session.requests == 1

    def test_default_page_and_limit_are_sent(self) -> None:
        _, _, session = run_cli(["get", "/repos/acme/widgets/pulls"],
                                responses=[json_response(PULLS)])
        assert "page=1&limit=20" in support.recorded(session)[0]["url"]

    def test_unknown_total_is_named_not_guessed(self) -> None:
        _, out, _ = run_cli(["get", "/repos/acme/widgets/pulls"],
                            responses=[json_response(PULLS)])
        assert out.splitlines()[:3] == ["count: 2", "total: unknown", "page: 1"]

    def test_empty_collection_is_definitive(self) -> None:
        code, out, _ = run_cli(["get", "/repos/acme/widgets/issues"],
                               responses=[json_response([])])
        assert code == 0
        assert out.splitlines()[0] == "count: 0"
        assert out.splitlines()[1] == "issues[0]{number,title,state,updated_at}:"

    def test_next_page_help_when_a_full_page_returns(self) -> None:
        rows = [dict(PULLS[0], number=n) for n in range(20)]
        _, out, _ = run_cli(["get", "/repos/acme/widgets/pulls", "state=open"],
                            responses=[json_response(rows, headers={"X-Total-Count": "83"})])
        assert "- gaxi get /repos/acme/widgets/pulls state=open page=2 limit=20" in out

    def test_wrapped_collection_is_recognised(self) -> None:
        payload = {"ok": True, "data": [{"id": 1, "name": "widgets", "status": "ready"}]}
        _, out, _ = run_cli(["get", "/repos/search", "q=widget"],
                            responses=[json_response(payload)])
        assert "repositories[1]{" in out

    def test_explicit_formats_encode_the_same_result(self) -> None:
        _, toon, _ = run_cli(["get", "/repos/acme/widgets/pulls"],
                             responses=[json_response(PULLS, headers={"X-Total-Count": "2"})])
        _, text, _ = run_cli(["get", "/repos/acme/widgets/pulls", "--output", "json"],
                             responses=[json_response(PULLS, headers={"X-Total-Count": "2"})])
        payload = json.loads(text)
        assert payload["count"] == 2
        assert payload["total"] == 2
        assert payload["pull_requests"][0]["title"] == "Fix race"
        assert "count: 2 of 2 total" in toon


class ProjectionTest(unittest.TestCase):
    def test_fields_replace_the_projection_in_caller_order(self) -> None:
        _, out, _ = run_cli(["get", "/repos/acme/widgets/pulls", "--fields", "title,number"],
                            responses=[json_response(PULLS)])
        assert "pull_requests[2]{title,number}:" in out
        assert "  Fix race,41" in out

    def test_unknown_field_is_a_validation_failure(self) -> None:
        code, out, _ = run_cli(["get", "/repos/acme/widgets/pulls", "--fields", "nope"],
                               responses=[json_response(PULLS)])
        assert code == 2
        assert "no response field named nope" in out

    def test_dotted_paths_select_nested_scalars(self) -> None:
        rows = [{"id": 3, "user": {"login": "alice"}, "created_at": "t"}]
        _, out, _ = run_cli(["get", "/repos/acme/widgets/issues/42/comments",
                             "--fields", "id,user.login"],
                            responses=[json_response(rows)])
        assert "comments[1]{id,user.login}:" in out
        assert "  3,alice" in out

    def test_absent_optional_field_emits_null(self) -> None:
        rows = [{"number": 41, "title": "Fix race"}]
        _, out, _ = run_cli(["get", "/repos/acme/widgets/pulls", "--fields", "number,state"],
                            responses=[json_response(rows)])
        assert "  41,null" in out


class TruncationTest(unittest.TestCase):
    LONG = "The deployment began failing after the runner upgrade " + "z" * 200

    def test_truncation_adds_metadata_and_an_executable_suggestion(self) -> None:
        _, out, _ = run_cli(["get", "/repos/acme/widgets/issues/42",
                             "--fields", "number,body"],
                            responses=[json_response({"number": 42, "body": self.LONG})])
        lines = out.splitlines()
        assert lines[2].endswith('…"')
        assert len(_quoted(lines[2])) == 160
        assert "truncated[1]{field,characters}:" in out
        assert f"  body,{len(self.LONG)}" in out
        assert "--fields number,body --full" in out

    def test_full_disables_truncation_without_adding_fields(self) -> None:
        _, out, _ = run_cli(["get", "/repos/acme/widgets/issues/42",
                             "--fields", "number,body", "--full"],
                            responses=[json_response({"number": 42, "body": self.LONG,
                                                      "title": "t"})])
        assert self.LONG in out
        assert "truncated[" not in out
        assert "title" not in out

    def test_collection_truncation_identifies_the_row(self) -> None:
        rows = [dict(PULLS[0]), dict(PULLS[1], body=self.LONG)]
        _, out, _ = run_cli(["get", "/repos/acme/widgets/pulls", "--fields", "number,body"],
                            responses=[json_response(rows)])
        assert "truncated[1]{row,field,characters}:" in out
        assert f"  2,body,{len(self.LONG)}" in out


class MutationTest(unittest.TestCase):
    def test_destructive_mutation_requires_yes_every_time(self) -> None:
        code, out, session = run_cli(["delete", "/repos/acme/widgets/issues/comments/17"])
        assert code == 1
        assert "requires --yes" in out
        assert "- gaxi delete /repos/acme/widgets/issues/comments/17 --yes" in out
        assert support.recorded(session) == []

    def test_acknowledged_delete_reports_a_status_result(self) -> None:
        code, out, _ = run_cli(["delete", "/repos/acme/widgets/issues/comments/17", "--yes"],
                               responses=[response(204, b"", media_type="")])
        assert code == 0
        assert "result:\n  status: 204\n  outcome: completed" in out

    def test_unknown_semantics_need_allow_unknown_not_yes(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".zip") as handle:
            argv = ["post", "/repos/acme/widgets/releases/3/assets",
                    f"attachment=@{handle.name}"]
            code, out, session = run_cli([*argv, "--yes"])
            assert code == 1
            assert "requires --allow-unknown" in out
            assert support.recorded(session) == []
            code, out, session = run_cli([*argv, "--allow-unknown"],
                                         responses=[json_response({"id": 5}, status=201)])
            assert code == 0

    def test_known_mutation_executes_without_acknowledgement(self) -> None:
        code, out, session = run_cli(
            ["post", "/repos/acme/widgets/issues", "title=Broken deployment"],
            responses=[json_response({"id": 999, "number": 42, "title": "Broken deployment",
                                      "state": "open", "updated_at": "t"}, status=201)])
        assert code == 0
        assert "issue:" in out
        assert "- gaxi get /repos/acme/widgets/issues/42" in out
        assert json.loads(support.recorded(session)[0]["body"]) == {"title": "Broken deployment"}

    def test_dry_run_sends_nothing_and_shows_context(self) -> None:
        code, out, session = run_cli(
            ["delete", "/repos/acme/widgets/issues/comments/17", "--yes", "--dry-run"])
        assert code == 0
        assert support.recorded(session) == []
        assert "  sent: false" in out
        assert "  confirmation: required" in out
        assert "  server_source: repository remote origin" in out
        assert "  repository: acme/widgets" in out


class TransportModeTest(unittest.TestCase):
    def test_text_is_structured_and_truncated(self) -> None:
        body = "diff --git a/x b/x\n" + "q" * 400
        code, out, _ = run_cli(["get", "/repos/acme/widgets/pulls/42.diff"],
                               responses=[response(200, body, media_type="text/plain")])
        assert code == 0
        assert "content:\n  media_type: text/plain" in out
        assert f"  size: {len(body)}" in out
        assert "  truncated: true" in out
        assert "- gaxi get /repos/acme/widgets/pulls/42.diff --raw" in out

    def test_raw_writes_the_exact_body_without_help(self) -> None:
        body = "diff --git a/x b/x\n"
        code, out, _ = run_cli(["get", "/repos/acme/widgets/pulls/42.diff", "--raw"],
                               responses=[response(200, body, media_type="text/plain")])
        assert code == 0
        assert out == body

    def test_advertised_binary_requires_save_or_raw_before_the_request(self) -> None:
        code, out, session = run_cli(["get", "/repos/acme/widgets/archive/main.zip"])
        assert code == 2
        assert "returns a binary response" in out
        assert support.recorded(session) == []

    def test_save_writes_atomically_and_prints_a_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "artifact.zip")
            code, out, _ = run_cli(
                ["get", "/repos/acme/widgets/archive/main.zip", "--save", path],
                responses=[response(200, b"PK\x03\x04payload",
                                    media_type="application/zip")])
            assert code == 0
            assert "file:" in out
            assert "  size: 11" in out
            assert "  media_type: application/zip" in out
            assert Path(path).is_file()
            assert [entry.name for entry in Path(directory).iterdir()] == ["artifact.zip"]

            code, out, _ = run_cli(
                ["get", "/repos/acme/widgets/archive/main.zip", "--save", path],
                responses=[response(200, b"other", media_type="application/zip")])
            assert code == 1
            assert "already exists" in out
            assert Path(path).read_bytes() == b"PK\x03\x04payload"

    def test_undocumented_binary_response_is_a_structured_error(self) -> None:
        code, out, _ = run_cli(["get", "/repos/acme/widgets/pulls/42"],
                               responses=[response(200, b"\x00\x01",
                                                   media_type="application/octet-stream")])
        assert code == 1
        assert "undocumented binary response" in out
        assert "--save" in out


class FailureTest(unittest.TestCase):
    def test_http_failure_is_structured_on_stdout(self) -> None:
        code, out, _ = run_cli(["get", "/repos/acme/widgets/issues/999"],
                               responses=[json_response({"message": "issue does not exist"},
                                                        status=404)])
        assert code == 1
        assert out.splitlines()[:4] == [
            "error:",
            "  message: issue does not exist",
            "  status: 404",
            "  request: GET /repos/acme/widgets/issues/999",
        ]
        assert "- gaxi get /repos/acme/widgets/issues" in out

    def test_authentication_failure_suggests_origin_scoped_setup(self) -> None:
        code, out, _ = run_cli(["get", "/user"],
                               responses=[json_response({"message": "token required"},
                                                        status=401)])
        assert code == 1
        assert "- gaxi auth add https://gitea.example.com" in out

    def test_unknown_command_exits_two(self) -> None:
        code, out, _ = run_cli(["frobnicate"])
        assert code == 2
        assert "unknown command frobnicate" in out

    def test_unknown_option_is_never_ignored(self) -> None:
        code, out, _ = run_cli(["get", "/user", "--invented"])
        assert code == 2
        assert "unknown option --invented" in out

    def test_path_must_be_api_relative(self) -> None:
        code, out, _ = run_cli(["get", "repos/acme/widgets/pulls"])
        assert code == 2
        assert "must begin with '/'" in out

    def test_ambiguous_resolution_sends_no_request(self) -> None:
        code, out, session = run_cli(["get", "/org/acme/widgets"])
        assert code == 1
        assert "2 capabilities match GET /org/acme/widgets" in out
        assert support.recorded(session) == []

    def test_selector_resolves_an_ambiguous_request(self) -> None:
        code, out, _ = run_cli(["get", "/org/acme/widgets",
                                "--as", "get:/org/{owner}/widgets"],
                               responses=[json_response([{"id": 1, "name": "a",
                                                          "status": "ready"}])])
        assert code == 0
        assert "widgets[1]{id,name,status" in out


class SurfaceTest(unittest.TestCase):
    def test_home_shows_live_state_not_usage(self) -> None:
        code, out, _session = run_cli(
            [], responses=[json_response([], headers={"X-Total-Count": "12"}),
                           json_response([], headers={"X-Total-Count": "3"})])
        assert code == 0
        assert "  repository: acme/widgets" in out
        assert "  open_issues: 12" in out
        assert "  open_pulls: 3" in out
        assert "- gaxi get /repos/acme/widgets/issues state=open" in out
        assert "usage" not in out

    def test_help_is_available_and_describes_real_flags(self) -> None:
        code, out, _ = run_cli(["get", "--help"])
        assert code == 0
        assert "  usage: gaxi get /path [name=value ...] [options]" in out
        assert "--allow-unknown" in out
        assert "examples[2]:" in out

    def test_capabilities_defaults_to_a_bounded_list(self) -> None:
        code, out, _ = run_cli(["capabilities"])
        assert code == 0
        assert out.splitlines()[0] == "count: 19 of 19 total"
        assert "capabilities[19]{method,path,summary,effect}:" in out

    def test_capability_reports_policy_provenance(self) -> None:
        code, out, _ = run_cli(["capability", "get:/repos/{owner}/{repo}/pulls"])
        assert code == 0
        assert "policy[6]{property,value,source}:" in out
        assert "  entity,pull_requests,builtin" in out

    def test_skill_is_generated_without_credentials(self) -> None:
        code, out, _ = run_cli(["skill"], env={"GITEA_SERVER": support.ORIGIN,
                                               "GITEA_TOKEN": "secret-token"})
        assert code == 0
        assert "name: gitea-axi-bridge" in out
        assert "gaxi get /repos/acme/widgets/issues state=open" in out
        assert "secret-token" not in out

    def test_version_reports_the_policy_bundle(self) -> None:
        code, out, _ = run_cli(["--version"])
        assert code == 0
        assert "  policy_bundle: " in out


def _quoted(line: str) -> str:
    return line.split(": ", 1)[1].strip('"')


if __name__ == "__main__":
    unittest.main()


class SetupAndRetryTest(unittest.TestCase):
    def test_setup_writes_the_skill_only_when_asked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "SKILL.md")
            code, out, _ = run_cli(["setup", "skill", "--path", path],
                                   repo=support.repository())
            assert code == 0
            assert "  outcome: written" in out
            assert "name: gitea-axi-bridge" in Path(path).read_text(encoding="utf-8")
            code, out, _ = run_cli(["setup", "skill", "--path", path])
            assert code == 1
            assert "already exists" in out

    def test_setup_installs_the_session_context_hook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.json")
            code, out, _ = run_cli(["setup", "hook", "--path", path])
            assert code == 0
            assert "  hook: SessionStart" in out
            settings = json.loads(Path(path).read_text(encoding="utf-8"))
            assert settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "gaxi context"
            code, out, _ = run_cli(["setup", "hook", "--path", path])
            assert "  outcome: unchanged" in out

    def test_safe_requests_retry_once(self) -> None:
        code, _out, session = run_cli(
            ["get", "/repos/acme/widgets/pulls"],
            responses=[response(503, b"", media_type="text/plain"),
                       json_response(PULLS, headers={"X-Total-Count": "2"})])
        assert code == 0
        assert len(support.recorded(session)) == 2

    def test_unsafe_requests_are_attempted_once(self) -> None:
        code, _out, session = run_cli(
            ["post", "/repos/acme/widgets/issues", "title=x"],
            responses=[response(503, b"", media_type="text/plain")])
        assert code == 1
        assert len(support.recorded(session)) == 1


class OutsideRepositoryTest(unittest.TestCase):
    def test_home_substitutes_instance_state_and_setup_actions(self) -> None:
        code, out, _ = run_cli([], repo=RepositoryContext(),
                               env={"GITEA_SERVER": support.ORIGIN})
        assert code == 0
        assert "  server: https://gitea.example.com" in out
        assert "  identity: anonymous" in out
        assert "repository:" not in out
        assert "- gaxi auth add https://gitea.example.com" in out

    def test_context_names_the_absent_repository(self) -> None:
        code, out, _ = run_cli(["context"], repo=RepositoryContext())
        assert code == 0
        assert "  repository: none" in out
        assert "  branch: none" in out


class InputSourceTest(unittest.TestCase):
    def test_input_json_from_a_file(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write('{"title": "From a file"}')
            path = handle.name
        try:
            code, _out, session = run_cli(
                ["post", "/repos/acme/widgets/issues", "--input-json", "@" + path],
                responses=[json_response({"number": 7, "title": "From a file",
                                          "state": "open", "updated_at": "t"}, status=201)])
        finally:
            Path(path).unlink()
        assert code == 0
        assert json.loads(support.recorded(session)[0]["body"]) == {"title": "From a file"}

    def test_put_verb_reaches_the_instance(self) -> None:
        document = {
            "swagger": "2.0", "basePath": "/api/v1",
            "paths": {"/user/starred/{owner}/{repo}": {"put": {
                "operationId": "userCurrentPutStar",
                "parameters": [
                    {"name": "owner", "in": "path", "type": "string", "required": True},
                    {"name": "repo", "in": "path", "type": "string", "required": True}],
                "responses": {"204": {"description": "APIEmpty"}}}}},
        }
        code, out, session = run_cli(["put", "/user/starred/acme/widgets"],
                                     document=document,
                                     responses=[response(204, b"", media_type="")])
        assert code == 0
        assert support.recorded(session)[0]["method"] == "PUT"
        assert "  status: 204" in out
