"""Local JSON report repository adapter.

This adapter keeps both a latest snapshot and a per-day history for account
reports and daily reports. That makes later push or audit workflows easier
without changing the application layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_trend_kit.domain.errors import StorageError
from trade_trend_kit.domain.models import AccountIncrementalReport, DailyReport
from trade_trend_kit.domain.ports import ReportRepository
from trade_trend_kit.utils.filenames import build_report_file_stem
from trade_trend_kit.utils.json_io import read_json_file, write_json_file

DEFAULT_REPORTS_DIR = Path("data/reports")


class JsonReportRepository(ReportRepository):
    """Persist account reports and daily reports as JSON files."""

    def __init__(self, base_dir: Path | str = DEFAULT_REPORTS_DIR) -> None:
        self.base_dir = Path(base_dir)

    async def save_account_report(self, report: AccountIncrementalReport) -> None:
        """Persist one account report snapshot and append to its history."""

        latest_path, history_path = self._account_report_paths(report)
        payload = report.model_dump(mode="json")
        self._write_latest(latest_path, payload)
        self._write_history(history_path, payload, key_field="report_id")

    async def save_daily_report(self, report: DailyReport) -> None:
        """Persist the current daily aggregate snapshot and append history."""

        latest_path, history_path = self._daily_report_paths(report)
        payload = report.model_dump(mode="json")
        self._write_latest(latest_path, payload)
        self._write_history(history_path, payload, key_field="updated_at")

    def _account_report_paths(
        self,
        report: AccountIncrementalReport,
    ) -> tuple[Path, Path]:
        stem = build_report_file_stem(report.market, report.category, report.account)
        report_dir = self.base_dir / report.date / "accounts"
        return (
            report_dir / f"{stem}.latest.json",
            report_dir / f"{stem}.history.json",
        )

    def _daily_report_paths(self, report: DailyReport) -> tuple[Path, Path]:
        report_dir = self.base_dir / report.date
        return (
            report_dir / "daily_report.json",
            report_dir / "daily_report.history.json",
        )

    def _write_latest(self, path: Path, payload: dict[str, Any]) -> None:
        """Write the latest report snapshot atomically."""

        write_json_file(path, payload)

    def _write_history(self, path: Path, payload: dict[str, Any], key_field: str) -> None:
        """Merge a report snapshot into the history file by a stable key."""

        history = self._load_history(path)
        merged: dict[str, dict[str, Any]] = {}
        for entry in [*history, payload]:
            key = entry.get(key_field)
            if key is None:
                raise StorageError(f"Report history entry is missing {key_field}: {path}")
            merged[str(key)] = entry
        write_json_file(path, list(merged.values()))

    def _load_history(self, path: Path) -> list[dict[str, Any]]:
        """Load an existing history file as a list of dicts."""

        raw_history = read_json_file(path, default=[])
        if raw_history in (None, []):
            return []
        if not isinstance(raw_history, list):
            raise StorageError(f"Report history file must contain a list: {path}")

        history: list[dict[str, Any]] = []
        for entry in raw_history:
            if not isinstance(entry, dict):
                raise StorageError(f"Report history entry must be an object: {path}")
            history.append(entry)
        return history
