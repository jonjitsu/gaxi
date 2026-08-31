"""Repository-wide Hypothesis profiles only.

Per-package fixtures belong in ``tests/<package>/conftest.py``.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

settings.register_profile("dev", max_examples=50)
settings.register_profile(
    "ci",
    max_examples=300,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile("thorough", max_examples=2000)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
