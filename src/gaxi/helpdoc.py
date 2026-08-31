"""Generated help.

Help is data: the same table drives `--help`, the home view, and `invoke docs`, so
documented flags, defaults, and output shapes cannot drift from the code.
"""

from __future__ import annotations

from typing import TypedDict

import gaxi
from gaxi.document import Document, Lines, Mapping, Scalar, Table
from gaxi.naming import executable
from gaxi.policy_data import BUNDLE_VERSION

type Option = tuple[str, str, str, str]


class CommandSpec(TypedDict):
    """One documented command: its grammar, its result, and its options."""

    usage: str
    summary: str
    output: str
    options: list[Option]
    examples: list[str]


GLOBAL_OPTIONS: list[Option] = [
    ("--server <origin>", "origin", "repository context", "Select the instance explicitly."),
    ("--output <format>", "toon|json|yaml", "toon",
     "Encode the same logical result in another format."),
    ("--anonymous", "flag", "false", "Send no credential even when one is bound to the origin."),
    ("--refresh", "flag", "false", "Re-fetch the instance description instead of using the cache."),
    ("--timeout <seconds>", "integer", "30", "HTTP timeout for one request."),
    ("--debug", "flag", "false", "Write incidental diagnostics to stderr."),
]

REQUEST_OPTIONS: list[Option] = [
    ("--fields <path,...>", "paths", "policy projection",
     "Replace the default projection, in caller order."),
    ("--full", "flag", "false", "Disable truncation for fields already projected."),
    ("--raw", "flag", "false", "Write the exact successful response body to stdout."),
    ("--save <path>", "path", "none", "Stream a response body to a file and print a receipt."),
    ("--overwrite", "flag", "false", "Allow --save to replace an existing file."),
    ("--input-json <json|@path|->", "json", "none", "Supply the complete JSON body."),
    ("--as <method:path-template>", "key", "none", "Disambiguate capability resolution."),
    ("--operation <operationId>", "id", "none", "Disambiguate by Swagger operationId."),
    ("--yes", "flag", "false", "Acknowledge a known destructive mutation."),
    ("--allow-unknown", "flag", "false", "Acknowledge a mutation with unknown semantics."),
    ("--dry-run", "flag", "false", "Resolve, bind, and validate without sending a request."),
]

DISCOVERY_OPTIONS: list[Option] = [
    ("--limit <n>", "integer", "20", "Rows per page of discovery output."),
    ("--page <n>", "integer", "1", "Page of discovery output."),
]

COMMANDS: dict[str, CommandSpec] = {
    "get": {
        "usage": "{exe} get /path [name=value ...] [options]",
        "summary": "Read one advertised capability by concrete API-relative path.",
        "output": "collection, detail object, content, or file receipt",
        "options": REQUEST_OPTIONS,
        "examples": [
            "{exe} get /repos/acme/widgets/pulls state=open limit=20",
            "{exe} get /repos/acme/widgets/issues/42 --fields number,title,body --full",
        ],
    },
    "post": {
        "usage": "{exe} post /path [name=value ...] [options]",
        "summary": "Create through one advertised capability.",
        "output": "detail object or status result",
        "options": REQUEST_OPTIONS,
        "examples": [
            '{exe} post /repos/acme/widgets/issues title="Broken deployment"',
            "{exe} post /repos/acme/widgets/issues --input-json @issue.json",
        ],
    },
    "put": {
        "usage": "{exe} put /path [name=value ...] [options]",
        "summary": "Replace through one advertised capability.",
        "output": "detail object or status result",
        "options": REQUEST_OPTIONS,
        "examples": ["{exe} put /user/starred/acme/widgets"],
    },
    "patch": {
        "usage": "{exe} patch /path [name=value ...] [options]",
        "summary": "Update through one advertised capability.",
        "output": "detail object or status result",
        "options": REQUEST_OPTIONS,
        "examples": ["{exe} patch /repos/acme/widgets/issues/42 state=closed"],
    },
    "delete": {
        "usage": "{exe} delete /path [name=value ...] --yes",
        "summary": "Delete through one advertised capability; always requires --yes.",
        "output": "status result",
        "options": REQUEST_OPTIONS,
        "examples": ["{exe} delete /repos/acme/widgets/issues/comments/17 --yes"],
    },
    "capabilities": {
        "usage": "{exe} capabilities [search terms] [options]",
        "summary": "List the capabilities this instance advertises.",
        "output": "capabilities[N]{method,path,summary,effect}",
        "options": DISCOVERY_OPTIONS,
        "examples": ["{exe} capabilities pull request", "{exe} capabilities delete issue"],
    },
    "capability": {
        "usage": "{exe} capability <key|operationId>",
        "summary":
            "Inspect one capability: inputs, responses, execution properties, policy source.",
        "output": "capability object with inputs[] and policy[]",
        "options": [],
        "examples": [
            "{exe} capability get:/repos/{owner}/{repo}/pulls",
            "{exe} capability repoListPullRequests",
        ],
    },
    "context": {
        "usage": "{exe} context",
        "summary": "Emit the compact ambient context an agent needs before acting.",
        "output": "context object with commands[]",
        "options": [],
        "examples": ["{exe} context"],
    },
    "skill": {
        "usage": "{exe} skill",
        "summary": "Generate repository-scoped Agent Skill guidance on stdout.",
        "output": "Markdown on stdout; no credential material",
        "options": [],
        "examples": ["{exe} skill > .claude/skills/gitea/SKILL.md"],
    },
    "setup": {
        "usage": "{exe} setup <skill|hook> [--path <file>] [--overwrite]",
        "summary": "Install the generated Agent Skill or the opt-in session-context hook.",
        "output": "status result naming the written path",
        "options": [
            ("--path <file>", "path",
             ".claude/skills/gitea-axi-bridge/SKILL.md or .claude/settings.json",
             "Destination to write."),
            ("--overwrite", "flag", "false", "Replace an existing skill file."),
        ],
        "examples": ["{exe} setup skill", "{exe} setup hook"],
    },
    "auth": {
        "usage": "{exe} auth <list|add|remove|allow-insecure> [origin]",
        "summary": "Bind credentials to an exact instance origin through a credential helper.",
        "output": "credentials[N]{origin,source,helper} or status result",
        "options": [
            ("--token-stdin", "flag", "required for add",
             "Read the token from stdin; never from an argument."),
            ("--helper <command>", "command", "configured helper",
             "External credential helper to store and read the token."),
        ],
        "examples": ["{exe} auth list", "{exe} auth add https://gitea.example.com --token-stdin"],
    },
}


def format_help(text: str) -> str:
    """Substitute the invoked executable name into a help template."""
    return text.replace("{exe}", executable())


def _options_table(options: list[Option]) -> Table:
    return Table(
        ["option", "value", "default", "description"],
        [list(option) for option in options],
    )


def command_help(name: str) -> Document:
    """The help document for one command, including the global options."""
    spec = COMMANDS[name]
    document = Document()
    mapping = Mapping()
    mapping.add("name", Scalar(name))
    mapping.add("usage", Scalar(format_help(spec["usage"])))
    mapping.add("summary", Scalar(spec["summary"]))
    mapping.add("output", Scalar(spec["output"]))
    document.add("command", mapping)
    options = spec["options"] + GLOBAL_OPTIONS
    document.add("options", _options_table(options))
    document.add("examples", Lines([format_help(example) for example in spec["examples"]]))
    return document


def verb_help(name: str) -> Document:
    """The help document for one request verb."""
    return command_help(name)


def root_help() -> Document:
    """The help document shown when no command is named."""
    document = Document()
    mapping = Mapping()
    mapping.add("executable", Scalar(executable()))
    mapping.add("version", Scalar(gaxi.__version__))
    mapping.add("summary", Scalar(
        "Turn a Gitea instance's advertised capabilities into compact, safe requests."))
    document.add("gaxi", mapping)
    document.add("commands", Table(
        ["command", "usage", "summary"],
        [[name, format_help(spec["usage"]), spec["summary"]] for name, spec in COMMANDS.items()],
    ))
    document.add("options", _options_table(GLOBAL_OPTIONS))
    document.add("help", Lines([
        f"{executable()} capabilities issue",
        f"{executable()} context",
    ]))
    return document


def version_document() -> Document:
    """The `--version` document: bridge, policy bundle, and description dialect."""
    document = Document()
    mapping = Mapping()
    mapping.add("name", Scalar(executable()))
    mapping.add("version", Scalar(gaxi.__version__))
    mapping.add("policy_bundle", Scalar(BUNDLE_VERSION))
    mapping.add("description_support", Scalar("swagger 2.0"))
    document.add("gaxi", mapping)
    return document
