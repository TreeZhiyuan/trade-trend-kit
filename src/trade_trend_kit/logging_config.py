"""Logging setup helpers.

Centralizing logging avoids each adapter inventing its own format and makes
future file/console logging changes easy to review.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final

DEFAULT_LOG_LEVEL: Final[str] = "INFO"


def configure_logging(
    level_name: str | None = None,
    log_file: str | Path | None = None,
) -> None:
    """Initialize project logging once for CLI and scheduler entry points."""

    level = _resolve_log_level(level_name)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    resolved_log_file = _resolve_log_file(log_file)
    if resolved_log_file is not None:
        resolved_log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(resolved_log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _resolve_log_level(level_name: str | None) -> int:
    value = (level_name or os.environ.get("LOG_LEVEL") or DEFAULT_LOG_LEVEL).strip().upper()
    level = getattr(logging, value, None)
    if isinstance(level, int):
        return level
    return logging.INFO


def _resolve_log_file(log_file: str | Path | None) -> Path | None:
    value = log_file or os.environ.get("LOG_FILE")
    if value is None or not str(value).strip():
        return None
    path = Path(str(value).strip())
    if not path.is_absolute():
        path = Path.cwd() / path
    return path
