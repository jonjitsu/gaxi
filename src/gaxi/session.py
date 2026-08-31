"""Session state shared by every command."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from gaxi import repo_context
from gaxi.config import Config, load_repo_overlay
from gaxi.credentials import CredentialResolver, redact
from gaxi.discovery import Instance, load_catalog, resolve_origin
from gaxi.policy import Policy
from gaxi.transport import Transport

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaxi.catalog import Catalog
    from gaxi.credentials import Credential
    from gaxi.repo_context import RepositoryContext
    from gaxi.transport import Exchange, Response

DEFAULT_TIMEOUT = 30


class Options:
    """Bridge options. Every option begins with `--`; API inputs never do."""

    def __init__(self, **values: object) -> None:
        self.server: str | None = None
        self.output: str = "toon"
        self.fields: list[str] | None = None
        self.full: bool = False
        self.raw: bool = False
        self.save: str | None = None
        self.overwrite: bool = False
        self.yes: bool = False
        self.allow_unknown: bool = False
        self.dry_run: bool = False
        self.anonymous: bool = False
        self.selector: str | None = None
        self.input_json: str | None = None
        self.refresh: bool = False
        self.debug: bool = False
        self.timeout: int = DEFAULT_TIMEOUT
        self.limit: int | None = None
        self.page: int | None = None
        self.helper: str | None = None
        self.token_stdin: bool = False
        self.__dict__.update(values)


class Session:
    """Lazily resolved instance, catalog, policy, and credential state."""

    def __init__(
        self,
        options: Options | None = None,
        transport: Exchange | None = None,
        env: Mapping[str, str] | None = None,
        cwd: str = ".",
        *,
        config: Config | None = None,
        repository: RepositoryContext | None = None,
        instance: Instance | None = None,
    ) -> None:
        self.options = options or Options()
        self.env = dict(env if env is not None else os.environ)
        self.cwd = cwd
        self.transport: Exchange = transport or Transport(timeout=self.options.timeout)
        self.requests = 0
        self._config = config
        self._repository = repository
        self._instance = instance
        self._policy: Policy | None = None
        self._credential: Credential | None = None
        self._credential_resolved = False

    @property
    def config(self) -> Config:
        """User configuration, loaded once."""
        if self._config is None:
            self._config = Config.load()
        return self._config

    @property
    def repository(self) -> RepositoryContext:
        """The repository the bridge was invoked in, discovered once."""
        if self._repository is None:
            self._repository = repo_context.discover(self.cwd)
        return self._repository

    @property
    def instance(self) -> Instance:
        """The resolved instance and its catalog, discovered once."""
        if self._instance is None:
            origin, source = resolve_origin(
                self.config, self.repository, self.options.server, self.env,
            )
            catalog, requests = load_catalog(
                origin, self.transport, refresh=self.options.refresh,
            )
            self.requests += requests
            self._instance = Instance(origin, source, catalog, requests)
        return self._instance

    @property
    def catalog(self) -> Catalog:
        """The capability catalog of the resolved instance."""
        return self.instance.catalog

    @property
    def policy(self) -> Policy:
        """The layered semantic policy for the resolved instance."""
        if self._policy is None:
            self._policy = Policy(
                user_overlay=self.config.overlay(self.instance.origin),
                repo_overlay=load_repo_overlay(self.repository.root),
            )
        return self._policy

    @property
    def credential(self) -> Credential | None:
        """The credential bound to the resolved origin, if any."""
        if not self._credential_resolved:
            resolver = CredentialResolver(self.config, self.env)
            self._credential = resolver.resolve(
                self.instance.origin, anonymous=self.options.anonymous,
            )
            resolver.check_transport(self.instance.origin, self._credential)
            self._credential_resolved = True
        return self._credential

    @property
    def secrets(self) -> list[str]:
        """Every secret that must be redacted from rendered text."""
        values = [self.env.get("GITEA_TOKEN")]
        if self._credential is not None:
            values.append(self._credential.token)
        return [value for value in values if value]

    def send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        *,
        stream: bool = False,
    ) -> Response:
        """Perform one request, counting it against this session."""
        self.requests += 1
        if self.options.debug:
            self.debug(f"{method.upper()} {url}")
        return self.transport.send(method, url, headers=headers, body=body, stream=stream)

    def debug(self, message: str) -> None:
        """Incidental diagnostics belong on stderr, never in the result."""
        if not self.options.debug:
            return
        sys.stderr.write("gaxi: " + redact(message, self.secrets) + "\n")
