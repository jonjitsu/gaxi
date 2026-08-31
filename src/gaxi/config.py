"""Configuration, origin normalization, and on-disk locations."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Self
from urllib.parse import urlsplit, urlunsplit

from gaxi.errors import GaxiError

if TYPE_CHECKING:
    from gaxi.jsonshape import JsonObject

DEFAULT_PORTS = {"http": 80, "https": 443}
ALLOWED_SCHEMES = ("http", "https")


def config_home() -> Path:
    """Where user configuration lives, honouring the XDG variables."""
    override = os.environ.get("GAXI_CONFIG_HOME")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "gaxi"


def cache_home() -> Path:
    """Where cached instance descriptions live, honouring the XDG variables."""
    override = os.environ.get("GAXI_CACHE_HOME")
    if override:
        return Path(override)
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "gaxi"


def normalize_origin(value: str | None) -> str:
    """Normalize an instance origin: scheme, host, effective port, base path."""
    if not value:
        msg = "an instance origin is required"
        raise GaxiError(msg)
    text = value.strip()
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ALLOWED_SCHEMES:
        msg = f"unsupported instance scheme {parts.scheme!r}"
        raise GaxiError(msg, details=[("server", value)])
    if not parts.hostname:
        msg = f"instance origin has no host: {value}"
        raise GaxiError(msg, details=[("server", value)])
    host = parts.hostname.lower()
    port = parts.port
    netloc = host if port in (None, DEFAULT_PORTS[parts.scheme]) else f"{host}:{port}"
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, netloc, path, "", ""))


class Config:
    """User configuration, loaded from `config.json` in the config home."""

    def __init__(self, data: JsonObject | None = None, path: Path | str | None = None) -> None:
        self.data: JsonObject = data or {}
        self.path = Path(path) if path is not None else config_home() / "config.json"

    @classmethod
    def load(cls, directory: Path | str | None = None) -> Self:
        """Read `config.json` from a directory, or return an empty configuration."""
        base = Path(directory) if directory is not None else config_home()
        path = base / "config.json"
        if not path.is_file():
            return cls({}, path)
        try:
            with path.open(encoding="utf-8") as handle:
                return cls(json.load(handle), path)
        except (OSError, json.JSONDecodeError) as exc:
            msg = f"cannot read configuration: {exc}"
            raise GaxiError(msg, details=[("path", str(path))]) from exc

    def save(self) -> None:
        """Write the configuration back through a temporary file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(self.data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temporary.replace(self.path)

    @property
    def default_server(self) -> str | None:
        """The configured default instance origin, normalized."""
        value = self.data.get("default_server")
        return normalize_origin(value) if value else None

    def servers(self) -> JsonObject:
        """Every configured instance, keyed by exact origin."""
        return dict(self.data.get("servers") or {})

    def server(self, origin: str) -> JsonObject:
        """The settings bound to one exact instance origin."""
        return dict(self.servers().get(origin) or {})

    def set_server(self, origin: str, values: JsonObject) -> None:
        """Merge settings into one exact instance origin."""
        servers = self.data.setdefault("servers", {})
        servers.setdefault(origin, {}).update(values)

    def overlay(self, origin: str) -> JsonObject:
        """The user overlay bound to one exact instance origin."""
        return dict((self.data.get("overlays") or {}).get(origin) or {})

    def ssh_origin(self, host: str) -> str | None:
        """An exact saved mapping from an SSH host to a web origin."""
        for origin, values in self.servers().items():
            for saved in values.get("ssh_hosts") or []:
                if saved.lower() == host.lower():
                    return origin
        return None

    def insecure_transport_allowed(self, origin: str) -> bool:
        """Whether plaintext HTTP was explicitly allowed for this origin."""
        return bool(self.server(origin).get("insecure_transport"))

    def credential_helper(self, origin: str) -> list[str] | None:
        """The credential helper command configured for this origin."""
        helper = self.server(origin).get("credential_helper")
        if isinstance(helper, str):
            return [helper]
        return list(helper) if helper else None


def load_repo_overlay(root: Path | str | None) -> JsonObject:
    """A repository-local presentation overlay, if the repository defines one."""
    if not root:
        return {}
    path = Path(root) / ".gaxi" / "overlay.json"
    if not path.is_file():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            loaded: JsonObject = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"cannot read repository overlay: {exc}"
        raise GaxiError(msg, details=[("path", str(path))]) from exc
    return loaded
