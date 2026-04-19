"""Environment helpers for integration recipes."""

from __future__ import annotations

import os


class EnvVarError(RuntimeError):
    """Raised when a required environment variable is missing."""


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvVarError(f"Missing required environment variable: {name}")
    return value

