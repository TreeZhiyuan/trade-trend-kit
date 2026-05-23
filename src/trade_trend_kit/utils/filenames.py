"""File name normalization helpers.

Storage adapters should use shared filename helpers to keep account files
consistent across raw tweets, normalized tweets, reports, and future exports.
"""

from __future__ import annotations

import re

SAFE_PART_PATTERN = re.compile(r"[^a-z0-9._-]+")
UNDERSCORE_PATTERN = re.compile(r"_+")


def normalize_filename_part(value: str) -> str:
    """Convert free-form text into a filesystem-safe lowercase fragment."""

    normalized = value.strip().lower()
    normalized = SAFE_PART_PATTERN.sub("_", normalized)
    normalized = UNDERSCORE_PATTERN.sub("_", normalized)
    normalized = normalized.strip("._-")
    return normalized or "unknown"


def build_file_stem(*parts: str) -> str:
    """Join multiple parts into one normalized filename stem."""

    joined = "_".join(part.strip() for part in parts if part and part.strip())
    return normalize_filename_part(joined)


def build_account_file_stem(file_key: str) -> str:
    """Normalize the canonical account key used in local file names."""

    return normalize_filename_part(file_key)


def build_report_file_stem(market: str, category: str, account: str) -> str:
    """Normalize report file names built from account attributes."""

    return build_file_stem(market, category, account)
