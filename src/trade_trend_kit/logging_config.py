"""Logging setup helpers.

Centralizing logging avoids each adapter inventing its own format and makes
future file/console logging changes easy to review.
"""

from __future__ import annotations

import logging
import os
from typing import Final

DEFAULT_LOG_LEVEL: Final[str] = "INFO"


def configure_logging(level_name: str | None = None) -> None:
    """Initialize project logging once for CLI and scheduler entry points."""

    level = _resolve_log_level(level_name)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _resolve_log_level(level_name: str | None) -> int:
    value = (level_name or os.environ.get("LOG_LEVEL") or DEFAULT_LOG_LEVEL).strip().upper()
    level = getattr(logging, value, None)
    if isinstance(level, int):
        return level
    return logging.INFO
