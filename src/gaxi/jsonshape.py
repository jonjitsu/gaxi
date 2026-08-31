"""The shape of decoded JSON, named once.

Values decoded from an instance are genuinely unconstrained, so these aliases
say `Any` deliberately rather than pretend to a stricter shape. Naming them
keeps that admission in one place instead of in every signature.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

type JsonValue = Any
type JsonObject = dict[str, Any]
type JsonMapping = Mapping[str, Any]
