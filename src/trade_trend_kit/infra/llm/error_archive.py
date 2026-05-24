"""Archive helpers for invalid LLM responses.

Keeping the archive format separate from the analyzer makes it easy to swap
the storage backend later without touching provider logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from trade_trend_kit.domain.models import AccountConfig
from trade_trend_kit.utils.filenames import build_file_stem, build_report_file_stem
from trade_trend_kit.utils.json_io import write_json_file
from trade_trend_kit.utils.time import date_key

DEFAULT_ERROR_ARCHIVE_DIR = Path("data/reports")


@dataclass(frozen=True)
class LLMErrorArchiveRecord:
    """Metadata captured when an OpenAI-compatible response cannot be used."""

    account: AccountConfig
    source_tweet_ids: list[str]
    stage: str
    error_message: str
    raw_response: str
    created_at: datetime
    timezone: str
    repair_response: str | None = None
    model: str | None = None


class LLMErrorArchive(Protocol):
    """Port for persisting unusable model responses for later review."""

    def save(self, record: LLMErrorArchiveRecord) -> Path:
        """Persist one archived failure and return the written path."""
        ...


class JsonLLMErrorArchive:
    """Persist invalid LLM responses as local JSON files."""

    def __init__(self, base_dir: Path | str = DEFAULT_ERROR_ARCHIVE_DIR) -> None:
        self.base_dir = Path(base_dir)

    def save(self, record: LLMErrorArchiveRecord) -> Path:
        """Write one failure record under the date/account archive tree."""

        path = self._path_for(record)
        payload = {
            "archive_type": "llm_error_response",
            "stage": record.stage,
            "error_message": record.error_message,
            "date": date_key(record.created_at, record.timezone),
            "timezone": record.timezone,
            "created_at": record.created_at.isoformat(),
            "account": {
                "account": record.account.account,
                "display_name": record.account.display_name,
                "market": record.account.market,
                "category": record.account.category,
                "region": record.account.region,
                "tags": list(record.account.tags),
                "watch_symbols": list(record.account.watch_symbols),
            },
            "source_tweet_ids": list(record.source_tweet_ids),
            "model": record.model,
            "raw_response": record.raw_response,
            "repair_response": record.repair_response,
        }
        write_json_file(path, payload)
        return path

    def _path_for(self, record: LLMErrorArchiveRecord) -> Path:
        stem = build_report_file_stem(
            record.account.market,
            record.account.category,
            record.account.account,
        )
        source_part = (
            build_file_stem(*record.source_tweet_ids[:3]) if record.source_tweet_ids else "empty"
        )
        timestamp = record.created_at.strftime("%Y%m%d%H%M%S%f")
        return (
            self.base_dir
            / date_key(record.created_at, record.timezone)
            / "errors"
            / f"{stem}_{timestamp}_{source_part}_{build_file_stem(record.stage)}.json"
        )
