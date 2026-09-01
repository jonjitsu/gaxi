"""Contextual disclosure: executable next-action suggestions (AXI rule 9).

One module owns ordering, de-duplication, the suggestion cap, and rendering
through ``naming.executable()``. Raising sites name an intent and supply
details; request-shaped sources such as ``Planner`` feed ``build()`` rather
than capping locally.
"""

from __future__ import annotations

from gaxi.document import Lines
from gaxi.naming import executable

MAX_SUGGESTIONS = 3


def collect(*commands: str | None) -> list[str]:
    """Order and de-duplicate without capping."""
    seen: set[str] = set()
    found: list[str] = []
    for candidate in commands:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        found.append(candidate)
    return found


def build(*commands: str | None) -> list[str]:
    """Order, de-duplicate, and cap suggestions."""
    return collect(*commands)[:MAX_SUGGESTIONS]


def prepend(first: str | None, *rest: str | None) -> list[str]:
    """Place one suggestion ahead of the rest."""
    return build(first, *rest)


def lines(*commands: str | None) -> Lines | None:
    """Render capped suggestions as document lines."""
    built = build(*commands)
    return Lines(built) if built else None


# bridge-level intents -------------------------------------------------------

def root_help() -> str:
    """Suggest the root usage document."""
    return f"{executable()} --help"


def subcommand_help(name: str) -> str:
    """Suggest one subcommand's usage document."""
    return f"{executable()} {name} --help"


def capability(key: str) -> str:
    """Suggest inspecting one capability."""
    return f"{executable()} capability {key}"


def capabilities(*terms: str, page: int | None = None) -> str:
    """Suggest searching or paging the capability catalog."""
    parts = [executable(), "capabilities", *terms]
    if page is not None:
        parts.extend(["--page", str(page)])
    return " ".join(parts)


def capabilities_example() -> str:
    """Suggest a concrete capability search."""
    return capabilities("issue")


def capabilities_placeholder() -> str:
    """Suggest searching with caller-supplied terms."""
    return f"{executable()} capabilities <search terms>"


def context(*, server: str | None = None) -> str:
    """Suggest inspecting ambient session context."""
    if server:
        return f"{executable()} --server {server} context"
    return f"{executable()} context"


def auth_add(origin: str) -> str:
    """Suggest binding a credential to one origin."""
    return f"{executable()} auth add {origin}"


def auth_add_stdin(origin: str) -> str:
    """Suggest storing a credential read from stdin."""
    return f"{executable()} auth add {origin} --token-stdin"


def auth_allow_insecure(origin: str) -> str:
    """Suggest allowing plaintext transport for one origin."""
    return f"{executable()} auth allow-insecure {origin}"


def auth_list() -> str:
    """Suggest listing configured credentials."""
    return f"{executable()} auth list"


def anonymous_get() -> str:
    """Suggest probing the instance without a credential."""
    return f"{executable()} get / --anonymous"


def setup_skill_overwrite() -> str:
    """Suggest overwriting an existing generated skill."""
    return f"{executable()} setup skill --overwrite"


def disambiguate(method: str, path: str, key: str) -> str:
    """Suggest naming the capability explicitly."""
    return f"{executable()} {method} {path} --as {key}"


def example_server_capabilities() -> str:
    """Suggest selecting an instance before discovery."""
    return f"{executable()} --server https://gitea.example.com capabilities"


def example_auth_add() -> str:
    """Suggest a concrete credential setup command."""
    return f"{executable()} auth add https://gitea.example.com --token-stdin"
