"""Instance discovery and description caching."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from gaxi.catalog import Catalog
from gaxi.config import cache_home, normalize_origin
from gaxi.errors import GaxiError
from gaxi.http import FIRST_SUCCESS, NOT_MODIFIED

if TYPE_CHECKING:
    from collections.abc import Mapping

    from gaxi.config import Config
    from gaxi.jsonshape import JsonObject
    from gaxi.repo_context import Remote, RepositoryContext
    from gaxi.transport import Exchange, Response

LogRequest = Callable[[str, str], None]

DISCOVERY_PATH = "/api/swagger"
FALLBACK_DOCUMENT = "/swagger.v1.json"
DATA_SOURCE = re.compile(r"""data-source\s*=\s*["']([^"']+)["']""")
DEFAULT_TTL = 3600
DIGEST_LENGTH = 32


class Instance:
    """One resolved instance: its origin, how it was selected, and its catalog."""

    def __init__(
        self,
        origin: str,
        source: str,
        catalog: Catalog,
        requests: int = 0,
    ) -> None:
        self.origin = origin
        self.source = source
        self.catalog = catalog
        self.requests = requests

    @property
    def version(self) -> str:
        """The instance version the description advertises."""
        return self.catalog.server_version

    def url(self, path: str, query: str = "") -> str:
        """One absolute URL for an API-relative path."""
        base = self.origin + self.catalog.base_path
        url = base.rstrip("/") + path
        return f"{url}?{query}" if query else url


def resolve_origin(
    config: Config,
    repository: RepositoryContext,
    server_option: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Select the instance origin, repository context first.

    1. an explicit `--server` value or the `GITEA_SERVER` session setting;
    2. repository context derived from the `origin` remote;
    3. the sole unambiguous configured Gitea remote;
    4. a configured default instance;
    5. otherwise a structured setup failure.
    """
    env = dict(env if env is not None else os.environ)
    if server_option:
        return normalize_origin(server_option), "option"
    if env.get("GITEA_SERVER"):
        return normalize_origin(env["GITEA_SERVER"]), "environment"
    from_repository = _repository_origin(config, repository)
    if from_repository is not None:
        return from_repository
    if config.default_server:
        return config.default_server, "configured default"
    msg = "no Gitea instance could be determined"
    raise GaxiError(
        msg,
        details=[("checked", "--server, GITEA_SERVER, git remotes, configured default")],
        help_commands=[
            "gaxi --server https://gitea.example.com capabilities",
            "gaxi context",
        ],
    )


def _repository_origin(
    config: Config,
    repository: RepositoryContext,
) -> tuple[str, str] | None:
    """The origin the ambient repository implies, when it implies exactly one."""
    if not repository.in_repository:
        return None
    remote = repository.origin_remote
    origin = _remote_origin(remote, config) if remote is not None else None
    if remote is not None and origin:
        return origin, f"repository remote {remote.name}"
    return _sole_remote_origin(config, repository)


def _sole_remote_origin(
    config: Config,
    repository: RepositoryContext,
) -> tuple[str, str] | None:
    """The origin of the only remote that maps to one, when there is exactly one."""
    mapped = [(other, _remote_origin(other, config)) for other in repository.remotes]
    candidates = {found for _, found in mapped if found}
    if len(candidates) != 1:
        return None
    named = next(other for other, found in mapped if found)
    return candidates.pop(), f"repository remote {named.name}"


def _remote_origin(remote: Remote, config: Config) -> str | None:
    if remote.origin:
        return remote.origin
    if remote.host:
        saved = config.ssh_origin(remote.host)
        if saved:
            return saved
        return normalize_origin("https://" + remote.host)
    return None


def _cache_path(origin: str, directory: Path | str | None = None) -> Path:
    digest = hashlib.sha256(origin.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]
    base = Path(directory) if directory is not None else cache_home()
    return base / f"{digest}.json"


def _read_cache(path: Path) -> JsonObject | None:
    try:
        with path.open(encoding="utf-8") as handle:
            cached: JsonObject = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return cached


def _write_cache(path: Path, payload: JsonObject) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        temporary.replace(path)
    except OSError:
        return


def _ttl() -> int:
    try:
        return int(os.environ.get("GAXI_CACHE_TTL", DEFAULT_TTL))
    except ValueError:
        return DEFAULT_TTL


def _send(
    transport: Exchange,
    method: str,
    url: str,
    headers: Mapping[str, str] | None = None,
    *,
    log_request: LogRequest | None = None,
) -> Response:
    if log_request is not None:
        log_request(method.upper(), url)
    return transport.send(method, url, headers=headers)


def load_catalog(
    origin: str,
    transport: Exchange,
    cache_dir: Path | str | None = None,
    *,
    refresh: bool = False,
    log_request: LogRequest | None = None,
) -> tuple[Catalog, int]:
    """Fetch and compile the instance description, using conditional caching.

    On a cold cache this usually performs two HTTP requests (discovery page and
    description document), totalling on the order of hundreds of kilobytes.
    Cached results are reused for ``GAXI_CACHE_TTL`` seconds (default 3600).
    """
    path = _cache_path(origin, cache_dir)
    cached = None if refresh else _read_cache(path)
    now = time.time()
    if cached and now - cached.get("fetched", 0) < _ttl():
        return Catalog.from_document(cached["document"], origin=origin), 0
    requests = 0
    if cached and cached.get("source_url"):
        revalidated = _revalidate(
            origin, transport, path, cached, now, log_request=log_request,
        )
        requests += 1
        if revalidated is not None:
            return revalidated, requests
    source_url, extra = _discover_document_url(
        origin, transport, log_request=log_request,
    )
    requests += extra
    response = _send(transport, "GET", source_url, log_request=log_request)
    requests += 1
    if response.status != FIRST_SUCCESS:
        msg = f"instance description request failed with status {response.status}"
        raise GaxiError(
            msg,
            status=response.status,
            details=[("request", f"GET {source_url}")],
            help_commands=[f"gaxi --server {origin} context"],
        )
    document = _parse_document(response, source_url)
    _store(path, origin, source_url, response, document, now)
    return Catalog.from_document(document, origin=origin), requests


def _conditional_headers(cached: JsonObject) -> dict[str, str]:
    """The validators the cached description was stored with."""
    headers: dict[str, str] = {}
    if cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    if cached.get("last_modified"):
        headers["If-Modified-Since"] = cached["last_modified"]
    return headers


def _revalidate(
    origin: str,
    transport: Exchange,
    path: Path,
    cached: JsonObject,
    now: float,
    *,
    log_request: LogRequest | None = None,
) -> Catalog | None:
    """Re-check a cached description; None when the instance did not answer usably."""
    source_url = cached["source_url"]
    response = _send(
        transport,
        "GET",
        source_url,
        headers=_conditional_headers(cached),
        log_request=log_request,
    )
    if response.status == NOT_MODIFIED:
        cached["fetched"] = now
        _write_cache(path, cached)
        return Catalog.from_document(cached["document"], origin=origin)
    if response.status == FIRST_SUCCESS:
        document = _parse_document(response, source_url)
        _store(path, origin, source_url, response, document, now)
        return Catalog.from_document(document, origin=origin)
    return None


def _store(
    path: Path,
    origin: str,
    source_url: str,
    response: Response,
    document: JsonObject,
    now: float,
) -> None:
    _write_cache(path, {
        "origin": origin,
        "source_url": source_url,
        "etag": response.headers.get("ETag"),
        "last_modified": response.headers.get("Last-Modified"),
        "fetched": now,
        "document": document,
    })


def _parse_document(response: Response, source_url: str) -> JsonObject:
    try:
        document = json.loads(response.read_all().decode(response.charset, "replace"))
    except (ValueError, UnicodeDecodeError) as exc:
        msg = f"instance description is not valid JSON: {exc}"
        raise GaxiError(msg, details=[("request", f"GET {source_url}")]) from exc
    if not isinstance(document, dict) or "paths" not in document:
        msg = "instance description declares no paths"
        raise GaxiError(msg, details=[("request", f"GET {source_url}")])
    if document.get("swagger", "").split(".")[0] not in {"2", ""}:
        msg = f"unsupported description version {document.get('swagger')}"
        raise GaxiError(
            msg,
            details=[("request", f"GET {source_url}"), ("supported", "swagger 2.0")],
        )
    return document


def _discover_document_url(
    origin: str,
    transport: Exchange,
    *,
    log_request: LogRequest | None = None,
) -> tuple[str, int]:
    """Resolve the description URL from the instance's discovery page."""
    discovery_url = origin + DISCOVERY_PATH
    response = _send(transport, "GET", discovery_url, log_request=log_request)
    body = response.read_all().decode(response.charset, "replace")
    if response.status == FIRST_SUCCESS:
        if response.media_type == "application/json":
            return discovery_url, 1
        found = DATA_SOURCE.search(body)
        if found:
            return urljoin(discovery_url, found.group(1)), 1
    return origin + FALLBACK_DOCUMENT, 1
