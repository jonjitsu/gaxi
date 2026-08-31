"""Origin-scoped credentials.

A credential is attached only when its bound origin exactly equals the resolved
request origin. Credential material is control-plane data: it is redacted from
every result, dry run, error, and debug log.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404  (the credential helper is an external command by design)
from typing import TYPE_CHECKING

from gaxi.config import normalize_origin
from gaxi.errors import GaxiError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from gaxi.config import Config

REDACTION = "<redacted>"


class Credential:
    """A token bound to one exact normalized origin."""

    def __init__(self, origin: str, token: str, source: str) -> None:
        self.origin = origin
        self.token = token
        self.source = source

    def headers(self) -> dict[str, str]:
        """The authorization header this credential contributes."""
        return {"Authorization": f"token {self.token}"}


class CredentialResolver:
    """Resolves the credential bound to a request origin, if any."""

    def __init__(self, config: Config, env: Mapping[str, str] | None = None) -> None:
        self.config = config
        self.env = dict(env if env is not None else os.environ)

    def environment_origin(self) -> str | None:
        """The origin `GITEA_SERVER` binds a token to, if it is set."""
        server = self.env.get("GITEA_SERVER")
        token = self.env.get("GITEA_TOKEN")
        if token and not server:
            msg = "GITEA_TOKEN is set without GITEA_SERVER"
            raise GaxiError(
                msg,
                details=[("expected", "GITEA_SERVER=<origin> GITEA_TOKEN=<secret>")],
                help_commands=["gaxi context"],
            )
        return normalize_origin(server) if server else None

    def resolve(self, origin: str, *, anonymous: bool = False) -> Credential | None:
        """The credential bound to this exact origin, or None."""
        if anonymous:
            return None
        environment = self.environment_origin()
        token = self.env.get("GITEA_TOKEN")
        if environment and token and environment == origin:
            return Credential(origin, token, "environment")
        helper_credential = self._from_helper(origin)
        if helper_credential:
            return helper_credential
        if environment and token and environment != origin:
            msg = "GITEA_TOKEN is bound to a different origin than the request"
            raise GaxiError(
                msg,
                details=[("credential_origin", environment), ("request_origin", origin)],
                help_commands=[
                    f"gaxi auth add {origin}",
                    "gaxi get / --anonymous",
                ],
            )
        return None

    def _from_helper(self, origin: str) -> Credential | None:
        helper = self.config.credential_helper(origin)
        if not helper:
            return None
        token = run_helper(helper, "get", origin)
        if not token:
            return None
        return Credential(origin, token, "credential-helper")

    def check_transport(self, origin: str, credential: Credential | None) -> None:
        """Refuse to send a credential over plaintext HTTP unless it was allowed."""
        plaintext = credential is not None and origin.startswith("http://")
        if plaintext and not self.config.insecure_transport_allowed(origin):
            msg = "refusing to send a credential over plaintext HTTP"
            raise GaxiError(
                msg,
                details=[("origin", origin)],
                help_commands=[f"gaxi auth allow-insecure {origin}"],
            )


def run_helper(
    helper: Sequence[str],
    action: str,
    origin: str,
    token: str | None = None,
) -> str | None:
    """Run an external credential helper: `<helper> <action> <origin>`."""
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [*helper, action, origin],
            input=(token + "\n") if token is not None else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        msg = f"credential helper failed: {exc}"
        details = [("helper", " ".join(helper)), ("action", action)]
        raise GaxiError(msg, details=details) from exc
    if completed.returncode != 0:
        if action == "get":
            return None
        msg = f"credential helper exited {completed.returncode}"
        raise GaxiError(
            msg,
            details=[("helper", " ".join(helper)), ("action", action)],
        )
    return completed.stdout.strip()


def redact(text: str, secrets: Iterable[str | None]) -> str:
    """Remove credential material from any rendered text."""
    if not text:
        return text
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTION)
    return text
