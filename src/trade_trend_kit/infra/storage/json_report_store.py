"""Local JSON report repository adapter.

This adapter keeps both a latest snapshot and a per-day history for account
reports and daily reports. That makes later push or audit workflows easier
without changing the application layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trade_trend_kit.domain.errors import StorageError
from trade_trend_kit.domain.models import AccountIncrementalReport, DailyReport, PublishPayload
from trade_trend_kit.domain.ports import ReportRepository
from trade_trend_kit.infra.publishing.payloads import build_daily_publish_payload
from trade_trend_kit.utils.filenames import build_file_stem, build_report_file_stem
from trade_trend_kit.utils.json_io import read_json_file, write_json_file, write_text_file
from trade_trend_kit.utils.report_rendering import (
    render_account_report_markdown,
    render_daily_report_markdown,
)

DEFAULT_REPORTS_DIR = Path("data/reports")
LOGGER = logging.getLogger(__name__)


class JsonReportRepository(ReportRepository):
    """Persist account and daily reports as JSON plus Markdown archives."""

    def __init__(self, base_dir: Path | str = DEFAULT_REPORTS_DIR) -> None:
        self.base_dir = Path(base_dir)

    async def save_account_report(self, report: AccountIncrementalReport) -> None:
        """Persist one account report snapshot and append to its history."""

        paths = self._account_report_paths(report)
        payload = report.model_dump(mode="json")
        markdown = render_account_report_markdown(report)
        self._write_latest(paths.latest_json, payload)
        self._write_latest_text(paths.latest_markdown, markdown)
        self._write_archive(paths.archive_json, payload)
        self._write_archive_text(paths.archive_markdown, markdown)
        self._write_history(paths.history_json, payload, key_field="report_id")
        LOGGER.info(
            "Account report files saved: account=%s date=%s latest_json=%s archive_json=%s",
            report.account,
            report.date,
            paths.latest_json,
            paths.archive_json,
        )

    async def save_daily_report(self, report: DailyReport) -> None:
        """Persist the current daily aggregate snapshot and append history."""

        paths = self._daily_report_paths(report)
        publish_paths = self._publish_payload_paths(report)
        payload = report.model_dump(mode="json")
        markdown = render_daily_report_markdown(report)
        publish_payload = build_daily_publish_payload(report)
        self._write_latest(paths.latest_json, payload)
        self._write_latest_text(paths.latest_markdown, markdown)
        self._write_archive(paths.archive_json, payload)
        self._write_archive_text(paths.archive_markdown, markdown)
        self._write_history(paths.history_json, payload, key_field="updated_at")
        self._write_publish_payload(publish_paths, publish_payload)
        LOGGER.info(
            "Daily report files saved: date=%s latest_json=%s archive_json=%s "
            "publish_json=%s",
            report.date,
            paths.latest_json,
            paths.archive_json,
            publish_paths.latest_json,
        )

    def _account_report_paths(
        self,
        report: AccountIncrementalReport,
    ) -> "_ReportArchivePaths":
        stem = build_report_file_stem(report.market, report.category, report.account)
        report_dir = self.base_dir / report.date / "accounts"
        archive_dir = report_dir / "archive"
        archive_stem = build_file_stem(stem, report.report_id)
        return _ReportArchivePaths(
            latest_json=report_dir / f"{stem}.latest.json",
            latest_markdown=report_dir / f"{stem}.latest.md",
            history_json=report_dir / f"{stem}.history.json",
            archive_json=archive_dir / f"{archive_stem}.json",
            archive_markdown=archive_dir / f"{archive_stem}.md",
        )

    def _daily_report_paths(self, report: DailyReport) -> "_ReportArchivePaths":
        report_dir = self.base_dir / report.date
        archive_dir = report_dir / "archive"
        archive_stem = build_file_stem("daily_report", report.updated_at.isoformat())
        return _ReportArchivePaths(
            latest_json=report_dir / "daily_report.json",
            latest_markdown=report_dir / "daily_report.md",
            history_json=report_dir / "daily_report.history.json",
            archive_json=archive_dir / f"{archive_stem}.json",
            archive_markdown=archive_dir / f"{archive_stem}.md",
        )

    def _publish_payload_paths(self, report: DailyReport) -> "_PublishPayloadPaths":
        report_dir = self.base_dir / report.date
        publish_dir = report_dir / "publish"
        archive_dir = publish_dir / "archive"
        archive_stem = build_file_stem("publish_payload", report.updated_at.isoformat())
        return _PublishPayloadPaths(
            latest_json=publish_dir / "publish_payload.json",
            latest_markdown=publish_dir / "publish_payload.md",
            latest_text=publish_dir / "publish_payload.txt",
            history_json=publish_dir / "publish_payload.history.json",
            archive_json=archive_dir / f"{archive_stem}.json",
            archive_markdown=archive_dir / f"{archive_stem}.md",
            archive_text=archive_dir / f"{archive_stem}.txt",
        )

    def _write_latest(self, path: Path, payload: dict[str, Any]) -> None:
        """Write the latest report snapshot atomically."""

        write_json_file(path, payload)

    def _write_latest_text(self, path: Path, text: str) -> None:
        """Write the latest Markdown snapshot atomically."""

        write_text_file(path, text)

    def _write_archive(self, path: Path, payload: dict[str, Any]) -> None:
        """Write an immutable JSON archive file for this report version."""

        write_json_file(path, payload)

    def _write_archive_text(self, path: Path, text: str) -> None:
        """Write an immutable Markdown archive file for this report version."""

        write_text_file(path, text)

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

    def _write_publish_payload(
        self,
        paths: "_PublishPayloadPaths",
        payload: PublishPayload,
    ) -> None:
        """Persist the push-ready daily payload in multiple reusable formats."""

        json_payload = payload.model_dump(mode="json")
        self._write_latest(paths.latest_json, json_payload)
        self._write_latest_text(paths.latest_markdown, payload.markdown_body)
        self._write_latest_text(paths.latest_text, payload.plain_text_body)
        self._write_archive(paths.archive_json, json_payload)
        self._write_archive_text(paths.archive_markdown, payload.markdown_body)
        self._write_archive_text(paths.archive_text, payload.plain_text_body)
        self._write_history(paths.history_json, json_payload, key_field="payload_id")

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


@dataclass(frozen=True)
class _ReportArchivePaths:
    """Paths written when saving one report version."""

    latest_json: Path
    latest_markdown: Path
    history_json: Path
    archive_json: Path
    archive_markdown: Path


@dataclass(frozen=True)
class _PublishPayloadPaths:
    """Paths written when saving one push-ready daily payload."""

    latest_json: Path
    latest_markdown: Path
    latest_text: Path
    history_json: Path
    archive_json: Path
    archive_markdown: Path
    archive_text: Path
