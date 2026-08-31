"""Explicit setup for opt-in session context and the generated Agent Skill.

Nothing is installed implicitly: `skill` and `context` only write files when a
caller runs this command.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from gaxi.commands import skill as skill_command
from gaxi.errors import GaxiError, UsageError
from gaxi.naming import executable
from gaxi.render import status_result

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gaxi.document import Document
    from gaxi.jsonshape import JsonObject
    from gaxi.session import Session

STATUS_OK = 200
ACTIONS = ("skill", "hook")
DEFAULT_SKILL_PATH = ".claude/skills/gitea-axi-bridge/SKILL.md"
DEFAULT_HOOK_PATH = ".claude/settings.json"


def run(session: Session, positionals: Sequence[str]) -> Document:
    """Install the generated skill or the opt-in session-context hook."""
    action = positionals[0] if positionals else None
    if action not in ACTIONS:
        msg = f"setup requires one of {', '.join(ACTIONS)}"
        raise UsageError(
            msg,
            details=[("usage", f"{executable()} setup skill --path {DEFAULT_SKILL_PATH}")],
        )
    root = Path(session.repository.root or Path.cwd())
    if action == "skill":
        return _write_skill(session, root)
    return _write_hook(session, root)


def _resolve(session: Session, root: Path, default: str) -> Path:
    return (root / (session.options.save or default)).absolute()


def _write_skill(session: Session, root: Path) -> Document:
    path = _resolve(session, root, DEFAULT_SKILL_PATH)
    if path.exists() and not session.options.overwrite:
        msg = f"{path} already exists"
        raise GaxiError(
            msg,
            details=[("path", str(path))],
            help_commands=[f"{executable()} setup skill --overwrite"],
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(skill_command.run(session), encoding="utf-8")
    return status_result(
        STATUS_OK,
        "written",
        extra=[("path", str(path)), ("kind", "agent skill")],
        help_commands=[f"{executable()} context"],
    )


def _write_hook(session: Session, root: Path) -> Document:
    path = _resolve(session, root, DEFAULT_HOOK_PATH)
    settings = _read_settings(path)
    hooks = settings.setdefault("hooks", {})
    entries = hooks.setdefault("SessionStart", [])
    wanted = {"hooks": [{"type": "command", "command": f"{executable()} context"}]}
    if wanted in entries:
        return status_result(
            STATUS_OK,
            "unchanged",
            extra=[("path", str(path))],
            help_commands=[f"{executable()} context"],
        )
    entries.append(wanted)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    return status_result(
        STATUS_OK,
        "installed",
        extra=[
            ("path", str(path)),
            ("hook", "SessionStart"),
            ("command", f"{executable()} context"),
        ],
        help_commands=[f"{executable()} context"],
    )


def _read_settings(path: Path) -> JsonObject:
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            settings: JsonObject = json.load(handle)
    except (OSError, ValueError) as exc:
        msg = f"cannot read {path}: {exc}"
        raise GaxiError(msg, details=[("path", str(path))]) from exc
    return settings
