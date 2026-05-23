from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trade_trend_kit.app.services import build_fake_fetch_job
from trade_trend_kit.domain.models import AccountConfig, RuntimeConfig
from trade_trend_kit.utils.json_io import read_json_file

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def fixed_clock(_: str) -> datetime:
    return datetime(2026, 5, 23, 10, 30, tzinfo=PROJECT_TZ)


def make_config() -> RuntimeConfig:
    return RuntimeConfig(
        timezone="Asia/Shanghai",
        tweet_limit=3,
        accounts=[
            AccountConfig(
                account="@macro_blogger",
                display_name="Macro Blogger",
                market="US_STOCK",
                category="macro",
                tags=["fed", "liquidity"],
                watch_symbols=["SPY", "QQQ"],
            )
        ],
    )


def test_fake_pipeline_generates_files_and_state_then_skips_existing_tweets(
    tmp_path: Path,
) -> None:
    config = make_config()
    job = build_fake_fetch_job(config=config, data_dir=tmp_path, clock=fixed_clock)

    first_summary = asyncio.run(job.run_once(config))
    second_summary = asyncio.run(job.run_once(config))

    stem = "us_stock_macro_macro_blogger"
    raw_payload = read_json_file(tmp_path / "raw_tweets" / "2026-05-23" / f"{stem}.json")
    normalized_payload = read_json_file(
        tmp_path / "normalized_tweets" / "2026-05-23" / f"{stem}.json"
    )
    account_latest = read_json_file(
        tmp_path / "reports" / "2026-05-23" / "accounts" / f"{stem}.latest.json"
    )
    account_history = read_json_file(
        tmp_path / "reports" / "2026-05-23" / "accounts" / f"{stem}.history.json"
    )
    daily_latest = read_json_file(tmp_path / "reports" / "2026-05-23" / "daily_report.json")
    daily_history = read_json_file(
        tmp_path / "reports" / "2026-05-23" / "daily_report.history.json"
    )
    state = read_json_file(tmp_path / "runtime" / "state.json")

    assert first_summary.processed_accounts == 1
    assert first_summary.fetched_tweet_count == 3
    assert first_summary.new_tweet_count == 3
    assert first_summary.generated_report_count == 1
    assert first_summary.daily_report_saved is True

    assert second_summary.fetched_tweet_count == 3
    assert second_summary.new_tweet_count == 0
    assert second_summary.generated_report_count == 0
    assert second_summary.daily_report_saved is False

    assert raw_payload["tweet_count"] == 3
    assert normalized_payload["tweet_count"] == 3
    assert account_latest["new_tweet_count"] == 3
    assert len(account_history) == 1
    assert account_latest["chinese_report"]["summary"].startswith("fake 分析")
    assert daily_latest["report_count"] == 1
    assert len(daily_history) == 1
    assert state["accounts"]["macro_blogger"]["consecutive_failures"] == 0
    assert len(state["accounts"]["macro_blogger"]["analyzed_tweet_ids"]) == 3


def test_fake_pipeline_respects_disabled_accounts(tmp_path: Path) -> None:
    config = RuntimeConfig(
        accounts=[
            AccountConfig(
                account="disabled_blogger",
                enabled=False,
                market="US_STOCK",
                category="macro",
            )
        ]
    )
    job = build_fake_fetch_job(config=config, data_dir=tmp_path, clock=fixed_clock)

    summary = asyncio.run(job.run_once(config))

    assert summary.processed_accounts == 0
    assert summary.skipped_accounts == 1
    assert summary.generated_report_count == 0
    assert read_json_file(tmp_path / "runtime" / "state.json") == {"accounts": {}}
