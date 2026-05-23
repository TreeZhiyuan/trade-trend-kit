"""Small helpers for loading key=value environment files.

The project uses `.env` files for local credentials, but we keep the parser
tiny and dependency-free so adapters can opt into it without extra packages.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path | str = Path(".env")) -> None:
    """Load a simple `.env` file into process environment variables."""

    env_path = Path(path)
    if not env_path.exists() or not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _unquote(value.strip())


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
