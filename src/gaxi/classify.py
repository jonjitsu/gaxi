"""The response classifier.

Classification uses the actual final status, headers, and content type, and
consults the advertised response only when runtime metadata is absent.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from gaxi.document import UNKNOWN
from gaxi.http import FIRST_FAILURE, FIRST_REDIRECT, FIRST_SUCCESS

if TYPE_CHECKING:
    from gaxi.jsonshape import JsonValue
    from gaxi.transport import Headers, Response

LINK_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
JSON_TYPES = ("application/json", "text/json")
TEXT_PREFIXES = ("text/",)
TEXT_TYPES = ("application/xml", "application/x-yaml", "application/javascript")


class Classification:
    """What a response actually is."""

    def __init__(
        self,
        kind: str,
        *,
        payload: JsonValue = None,
        media_type: str = "",
        status: int = FIRST_SUCCESS,
        total: int | str | None = None,
        page: int | None = None,
        has_next: bool = False,
    ) -> None:
        self.kind = kind
        self.payload = payload
        self.media_type = media_type
        self.status = status
        self.total = total
        self.page = page
        self.has_next = has_next


def _is_json(media_type: str, advertised_kind: str) -> bool:
    if media_type:
        return media_type in JSON_TYPES or media_type.endswith("+json")
    return advertised_kind in {"collection", "object"}


def _is_text(media_type: str, advertised_kind: str) -> bool:
    if media_type:
        return media_type.startswith(TEXT_PREFIXES) or media_type in TEXT_TYPES
    return advertised_kind == "text"


def classify(
    response: Response,
    advertised_kind: str = "unknown",
    page: int | None = None,
) -> Classification:
    """Classify one response against its advertised shape."""
    status = response.status
    media_type = response.media_type
    body = response.read_all()

    if FIRST_REDIRECT <= status < FIRST_FAILURE:
        return Classification(
            "redirect",
            payload=response.headers.get("Location"),
            media_type=media_type,
            status=status,
        )
    if status >= FIRST_FAILURE:
        payload = _maybe_json(body, response.charset) if _is_json(media_type, "object") else None
        return Classification("error", payload=payload, media_type=media_type, status=status)
    if not body:
        return Classification("status", media_type=media_type, status=status)
    if _is_json(media_type, advertised_kind):
        return _classify_json(response, body, advertised_kind, page=page)
    if _is_text(media_type, advertised_kind):
        return Classification(
            "text",
            payload=_text(body, response.charset),
            media_type=media_type or "text/plain",
            status=status,
        )
    return Classification(
        "binary",
        payload=body,
        media_type=media_type or "application/octet-stream",
        status=status,
    )


def _classify_json(
    response: Response,
    body: bytes,
    advertised_kind: str,
    *,
    page: int | None,
) -> Classification:
    status = response.status
    media_type = response.media_type
    payload = _maybe_json(body, response.charset)
    if payload is None:
        return Classification(
            "text",
            payload=_text(body, response.charset),
            media_type=media_type or "text/plain",
            status=status,
        )
    total = _collection_total(_total(response.headers), page)
    has_next = bool(LINK_NEXT.search(response.headers.get("Link", "") or ""))
    items = payload if isinstance(payload, list) else None
    if items is None and advertised_kind == "collection":
        items = _unwrap(payload)
    if items is not None:
        return Classification(
            "collection",
            payload=items,
            media_type=media_type,
            status=status,
            total=total,
            page=page,
            has_next=has_next,
        )
    return Classification("object", payload=payload, media_type=media_type, status=status)


def _collection_total(total: int | str | None, page: int | None) -> int | str | None:
    if total is not None:
        return total
    return UNKNOWN if page is not None else None


def _unwrap(payload: JsonValue) -> list[JsonValue] | None:
    for key in ("data", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def _total(headers: Headers) -> int | str | None:
    raw = headers.get("X-Total-Count")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return UNKNOWN


def _maybe_json(body: bytes, charset: str) -> JsonValue:
    try:
        return json.loads(body.decode(charset, "replace"))
    except (ValueError, UnicodeDecodeError):
        return None


def _text(body: bytes, charset: str) -> str:
    return body.decode(charset, "replace")
