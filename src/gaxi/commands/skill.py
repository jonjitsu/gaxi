"""Agent Skill generation.

The skill is generated from the same command templates and resolved capability
vocabulary the bridge uses at runtime. It is written to stdout, contains no
credential material, and installs nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from gaxi.commands import context as context_command
from gaxi.naming import command, executable

if TYPE_CHECKING:
    from gaxi.session import Session

VOCABULARY = [
    ("list issues", "get", "/repos/{repo}/issues", [("state", "open")]),
    ("read one issue", "get", "/repos/{repo}/issues/<index>", []),
    ("comment on an issue", "post", "/repos/{repo}/issues/<index>/comments", [("body", "<text>")]),
    ("list pull requests", "get", "/repos/{repo}/pulls", [("state", "open")]),
    ("read one pull request", "get", "/repos/{repo}/pulls/<index>", []),
    ("list labels", "get", "/repos/{repo}/labels", []),
]


def _batch_example(full_name: str) -> str:
    """One batched create, addressed to the ambient repository when there is one."""
    repo = full_name or "<owner>/<repo>"
    return (
        f"{executable()} post /repos/{repo}/issues "
        '--input-json \'[{"title":"First"},{"title":"Second"}]\''
    )


def run(session: Session) -> str:
    """Render the Agent Skill for this instance and repository context."""
    exe = executable()
    full_name = context_command.repository_identity(session)
    origin = session.instance.origin
    catalog = session.catalog
    lines = [
        "---",
        "name: gitea-axi-bridge",
        (f"description: Query and mutate {origin} through {exe}, an AXI bridge over the "
        "instance's advertised capabilities. Use for issues, pull requests, labels, "
        "releases, and any other advertised Gitea capability."),
        "---",
        "",
        "# Gitea AXI bridge",
        "",
        (f"`{exe}` turns one concrete API-relative path into exactly one advertised "
        f"capability on `{origin}` (Gitea {session.instance.version or 'unknown'}, "
        f"{len(catalog.available())} capabilities)."),
        "",
        "## Request grammar",
        "",
        "```text",
        f"{exe} <get|post|put|patch|delete> /api-relative/path [name=value ...] [--options]",
        "```",
        "",
        ("- The path is relative to the instance base path; it never includes the origin "
        "or `/api/v1`."),
        ("- API inputs are `name=value` arguments. Options always begin with `--`, so an "
        "input named `output` cannot collide with `--output`."),
        "- Qualify an ambiguous input with `query:`, `body:`, or `form:`.",
        "- Repeat an assignment for array inputs; use `--input-json` for nested bodies.",
        "",
        "## Batch mutations",
        "",
        ("`--input-json` accepts a JSON array or NDJSON as well as one object. One "
        "invocation then sends one request per body, so N creates cost one command "
        "instead of N."),
        "",
        "```text",
        _batch_example(full_name),
        "```",
        "",
        "- The result is a collection with one row per body, in the order supplied.",
        ("- A failing element does not abort the batch: its row carries `error` and "
        "`status`, and the invocation exits non-zero."),
        ("- `--yes` is given once for the whole invocation; `--save` and `--raw` are "
        "rejected for batches."),
        "",
        "## Output contract",
        "",
        ("- Collections emit `count: N of M total` before a named typed table; empty "
        "results emit `count: 0` and a zero-row table."),
        ("- Strings are truncated at 160 characters with `truncated[]` metadata; use "
        "`--fields` and `--full` to read a complete value."),
        ("- Projections list dropped response fields in `omitted[]`; use `--fields` to "
        "include them."),
        ("- Failures are structured on stdout with exit 1; validation failures exit 2 "
        "before any request is sent."),
        "- `help[]` lists the next executable commands.",
        "",
        "## Safety",
        "",
        "- Known destructive mutations require `--yes` on every invocation.",
        "- Mutations whose semantics policy does not know require `--allow-unknown`.",
        "- Nothing ever prompts; `--dry-run` validates without sending a request.",
        "",
        "## Commands for this context",
        "",
        "```text",
    ]
    lines.extend(context_command.command_templates(full_name))
    lines.append("```")
    lines.append("")
    if full_name:
        lines.extend(["## Capability vocabulary", "", "```text"])
        for label, method, template, assignments in VOCABULARY:
            path = template.replace("{repo}", full_name)
            if catalog.match(method, path.replace("<index>", "1")):
                lines.append(f"# {label}")
                lines.append(command(method, path, assignments))
        lines.append("```")
        lines.append("")
    lines.extend([
        "## Discovery",
        "",
        "```text",
        f"{exe} capabilities <search terms>",
        f"{exe} capability <method:path-template|operationId>",
        f"{exe} context",
        "```",
        "",
        ("Credentials are bound to an exact instance origin and are never printed by "
        "this tool."),
        "",
    ])
    return "\n".join(lines)
