"""Command-line surface.

Options always begin with `--` and belong to the bridge; API inputs are
`name=value` arguments, so an input named `output` never collides with the
bridge's `--output` option.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO, TYPE_CHECKING

from gaxi import helpdoc, render
from gaxi.commands import auth as auth_command
from gaxi.commands import capabilities as capabilities_command
from gaxi.commands import context as context_command
from gaxi.commands import home as home_command
from gaxi.commands import setup as setup_command
from gaxi.commands import skill as skill_command
from gaxi.credentials import redact
from gaxi.document import Document
from gaxi.encode import encode
from gaxi.errors import EXIT_FAILURE, GaxiError, UsageError
from gaxi.invocation import Outcome
from gaxi.invoke import run_request
from gaxi.naming import executable
from gaxi.session import Options, Session

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from gaxi.jsonshape import JsonObject

VERBS = ("get", "post", "put", "patch", "delete")
COMMANDS = (*VERBS, "capabilities", "capability", "context", "skill", "setup", "auth")

VALUE_OPTIONS = {
    "--server": "server",
    "--output": "output",
    "--fields": "fields",
    "--save": "save",
    "--path": "save",
    "--as": "selector",
    "--operation": "selector",
    "--input-json": "input_json",
    "--timeout": "timeout",
    "--limit": "limit",
    "--page": "page",
    "--helper": "helper",
}
FLAG_OPTIONS = {
    "--full": "full",
    "--raw": "raw",
    "--overwrite": "overwrite",
    "--yes": "yes",
    "--allow-unknown": "allow_unknown",
    "--dry-run": "dry_run",
    "--anonymous": "anonymous",
    "--refresh": "refresh",
    "--debug": "debug",
    "--token-stdin": "token_stdin",
}
OUTPUT_FORMATS = ("toon", "json", "yaml")


class Invocation:
    """A parsed command line."""

    def __init__(
        self,
        name: str | None = None,
        positionals: Sequence[str] = (),
        options: Options | None = None,
        *,
        wants_help: bool = False,
        wants_version: bool = False,
    ) -> None:
        self.name = name
        self.positionals = list(positionals)
        self.options = options or Options()
        self.wants_help = wants_help
        self.wants_version = wants_version


def parse(argv: Sequence[str]) -> Invocation:
    """Parse a command line without letting API inputs reach option parsing."""
    values: JsonObject = {}
    positionals: list[str] = []
    wants_help = False
    wants_version = False
    index = 0
    while index < len(argv):
        argument = argv[index]
        index += 1
        if argument in {"--help", "-h"}:
            wants_help = True
        elif argument == "--version":
            wants_version = True
        elif argument.startswith("--"):
            index = _consume_option(argument, argv, index, values)
        elif argument.startswith("-") and len(argument) > 1 and not argument[1].isdigit():
            msg = f"unknown option {argument}"
            raise UsageError(
                msg,
                details=[("option", argument)],
                help_commands=[f"{executable()} --help"],
            )
        else:
            positionals.append(argument)

    name = positionals.pop(0) if positionals else None
    return Invocation(
        name,
        positionals,
        _options(values),
        wants_help=wants_help,
        wants_version=wants_version,
    )


def _consume_option(argument: str, argv: Sequence[str], index: int, values: JsonObject) -> int:
    """Record one `--option`, returning the index of the next argument."""
    name, separator, inline = argument.partition("=")
    if name in FLAG_OPTIONS:
        if separator:
            msg = f"{name} does not take a value"
            raise UsageError(msg)
        values[FLAG_OPTIONS[name]] = True
        return index
    if name not in VALUE_OPTIONS:
        msg = f"unknown option {name}"
        raise UsageError(
            msg,
            details=[("option", name)],
            help_commands=[f"{executable()} --help"],
        )
    if separator:
        values[VALUE_OPTIONS[name]] = inline
        return index
    if index >= len(argv):
        msg = f"{name} requires a value"
        raise UsageError(msg)
    values[VALUE_OPTIONS[name]] = argv[index]
    return index + 1


INTEGER_OPTIONS = ("timeout", "limit", "page")


def _options(values: JsonObject) -> Options:
    if "fields" in values:
        values["fields"] = [f.strip() for f in values["fields"].split(",") if f.strip()]
    for key in INTEGER_OPTIONS:
        if key in values:
            values[key] = _positive_int(values[key], f"--{key}")
    if "input_json" in values:
        values["input_json"] = _read_input_json(values["input_json"])
    _check_output_format(values.get("output", "toon"))
    return Options(**values)


def _check_output_format(output: str) -> None:
    if output in OUTPUT_FORMATS:
        return
    msg = f"unknown output format {output}"
    raise UsageError(msg, details=[("supported", ", ".join(OUTPUT_FORMATS))])


def _positive_int(value: str, name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        msg = f"{name} expects an integer, got {value!r}"
        raise UsageError(msg) from exc
    if number <= 0:
        msg = f"{name} expects a positive integer, got {value!r}"
        raise UsageError(msg)
    return number


def _read_input_json(value: str) -> str:
    if value == "-":
        return sys.stdin.read()
    if value.startswith("@"):
        path = value[1:]
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            msg = f"cannot read --input-json file: {exc}"
            raise UsageError(msg, details=[("path", path)]) from exc
    return value


def _run_verb(invocation: Invocation, session: Session, name: str) -> Outcome:
    if not invocation.positionals:
        msg = f"{name} requires one API-relative path"
        raise UsageError(
            msg,
            details=[("usage", f"{executable()} {name} /path name=value")],
            help_commands=[f"{executable()} {name} --help"],
        )
    path, *assignments = invocation.positionals
    return run_request(session, name, path, assignments)


def _run_capabilities(invocation: Invocation, session: Session) -> Outcome:
    return Outcome(capabilities_command.run(session, invocation.positionals))


def _run_capability(invocation: Invocation, session: Session) -> Outcome:
    if len(invocation.positionals) != 1:
        usage = f"{executable()} capability get:/repos/{{owner}}/{{repo}}/pulls"
        msg = "capability requires one key or operationId"
        raise UsageError(msg, details=[("usage", usage)])
    return Outcome(capabilities_command.detail(session, invocation.positionals[0]))


def _run_context(invocation: Invocation, session: Session) -> Outcome:
    del invocation
    return Outcome(context_command.run(session))


def _run_skill(invocation: Invocation, session: Session) -> Outcome:
    del invocation
    return Outcome(raw=skill_command.run(session).encode("utf-8"))


def _run_setup(invocation: Invocation, session: Session) -> Outcome:
    return Outcome(setup_command.run(session, invocation.positionals))


def _run_auth(invocation: Invocation, session: Session) -> Outcome:
    return Outcome(auth_command.run(session, invocation.positionals))


HANDLERS: dict[str, Callable[[Invocation, Session], Outcome]] = {
    "capabilities": _run_capabilities,
    "capability": _run_capability,
    "context": _run_context,
    "skill": _run_skill,
    "setup": _run_setup,
    "auth": _run_auth,
}


def dispatch(invocation: Invocation, session: Session) -> Outcome:
    """Run one parsed invocation."""
    name = invocation.name
    if invocation.wants_version:
        return Outcome(helpdoc.version_document())
    if name is None:
        document = helpdoc.root_help() if invocation.wants_help else home_command.run(session)
        return Outcome(document)
    if name in VERBS:
        if invocation.wants_help:
            return Outcome(helpdoc.verb_help(name))
        return _run_verb(invocation, session, name)
    handler = HANDLERS.get(name)
    if handler is None:
        msg = f"unknown command {name}"
        raise UsageError(
            msg,
            details=[("command", name), ("known", ", ".join(COMMANDS))],
            help_commands=[f"{executable()} --help"],
        )
    if invocation.wants_help:
        return Outcome(helpdoc.command_help(name))
    return handler(invocation, session)


def main(
    argv: Sequence[str] | None = None,
    session: Session | None = None,
    stdout: IO[str] | None = None,
) -> int:
    """Entry point. Structured output always leaves on stdout."""
    argv = list(sys.argv[1:] if argv is None else argv)
    stream = stdout or sys.stdout
    secrets: list[str] = []
    try:
        invocation = parse(argv)
        session = session or Session(invocation.options)
        session.options = invocation.options
        outcome = dispatch(invocation, session)
        secrets = session.secrets
    except GaxiError as exc:
        if session is not None:
            secrets = session.secrets
        _write_document(stream, _error_document(exc), Options(), secrets)
        return exc.exit_code
    except KeyboardInterrupt:
        _write_document(stream, _error_document(GaxiError("interrupted")), Options(), [])
        return EXIT_FAILURE
    if outcome.raw is not None:
        _write_raw(stream, outcome.raw)
        return outcome.exit_code
    _write_document(stream, outcome.document or Document(), invocation.options, secrets)
    return outcome.exit_code


def _error_document(exc: GaxiError) -> Document:
    return render.error(
        exc.message,
        status=exc.status,
        request=exc.request,
        details=exc.details,
        help_commands=exc.help_commands,
    )


def _write_document(
    stream: IO[str],
    document: Document,
    options: Options,
    secrets: Sequence[str],
) -> None:
    stream.write(redact(encode(document, options.output), secrets) + "\n")


def _write_raw(stream: IO[str], payload: bytes) -> None:
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        buffer.write(payload)
        buffer.flush()
    else:
        stream.write(payload.decode("utf-8", "replace"))


if __name__ == "__main__":
    raise SystemExit(main())
