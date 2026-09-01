"""Invoke entry point: the tasks themselves live in `automation/ci/tasks`.

The automation package sits outside `src/` so it is never part of the
distribution, which also means it is not installed and has to be put on the path
before the collection can be imported.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "automation"))

from ci.tasks import ns

__all__ = ["ns"]
