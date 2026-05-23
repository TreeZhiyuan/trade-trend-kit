from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trade_trend_kit.app.fetch_job import FetchCycleSummary
from trade_trend_kit.config import load_config
from trade_trend_kit.scheduler import (
    SCHEDULED_JOB_ID,
    ScheduledCollector,
    ScheduledRunSettings,
    run_collection_once,
)
from trade_trend_kit.utils.json_io import read_json_file

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def fixed_clock(_: str) -> datetime:
    return datetime(2026, 5, 23, 10, 0, tzinfo=PROJECT_TZ)


def write_config(path: Path, interval_minutes: int = 15, account_count: int = 1) -> None:
    accounts = [
        {
            "account": f"scheduler_blogger_{index}",
            "display_name": f"Scheduler Blogger {index}",
            "enabled": True,
            "market": "US_STOCK",
            "category": "macro",
            "tags": ["fed"],
            "watch_symbols": ["SPY"],
        }
        for index in range(account_count)
    ]
    path.write_text(
        json.dumps(
            {
                "timezone": "Asia/Shanghai",
                "fetch_interval_minutes": interval_minutes,
                "tweet_limit": 2,
                "analysis_language": "zh-CN",
                "preserve_english_summary": True,
                "accounts": accounts,
            }
        ),
        encoding="utf-8",
    )


def test_configure_adds_interval_job_with_overlap_protection(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    write_config(config_path, interval_minutes=15)
    settings = ScheduledRunSettings(
        config_path=config_path,
        data_dir=tmp_path / "data",
        source="fake",
    )
    collector = ScheduledCollector(settings=settings, clock=fixed_clock)

    job = collector.configure(load_config(config_path))

    assert job.id == SCHEDULED_JOB_ID
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.trigger.interval.total_seconds() == 15 * 60
    assert collector.scheduler is not None
    assert collector.scheduler.get_job(SCHEDULED_JOB_ID) is job


def test_safe_run_cycle_refreshes_schedule_when_interval_changes(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    write_config(config_path, interval_minutes=15)
    settings = ScheduledRunSettings(
        config_path=config_path,
        data_dir=tmp_path / "data",
        source="fake",
    )
    collector = ScheduledCollector(
        settings=settings,
        cycle_runner=lambda _: completed_summary(),
        clock=fixed_clock,
    )
    collector.configure(load_config(config_path))
    write_config(config_path, interval_minutes=5)

    asyncio.run(collector._safe_run_cycle())

    assert collector.scheduler is not None
    job = collector.scheduler.get_job(SCHEDULED_JOB_ID)
    assert job is not None
    assert job.trigger.interval.total_seconds() == 5 * 60


def test_run_cycle_skips_when_previous_cycle_is_active(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    write_config(config_path)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def slow_runner(_: ScheduledRunSettings) -> FetchCycleSummary:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return FetchCycleSummary(
            processed_accounts=1,
            skipped_accounts=0,
            fetched_tweet_count=0,
            new_tweet_count=0,
            generated_report_count=0,
            daily_report_saved=False,
        )

    async def scenario() -> None:
        collector = ScheduledCollector(
            settings=ScheduledRunSettings(config_path=config_path, source="fake"),
            cycle_runner=slow_runner,
        )
        first_task = asyncio.create_task(collector.run_cycle())
        await started.wait()

        skipped = await collector.run_cycle()
        release.set()
        first_result = await first_task

        assert skipped is None
        assert first_result is not None

    asyncio.run(scenario())

    assert calls == 1


def test_run_collection_once_reloads_config_and_executes_fake_pipeline(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    data_dir = tmp_path / "data"
    write_config(config_path, interval_minutes=15, account_count=1)
    settings = ScheduledRunSettings(
        config_path=config_path,
        data_dir=data_dir,
        source="fake",
    )

    first_summary = asyncio.run(run_collection_once(settings))
    write_config(config_path, interval_minutes=15, account_count=2)
    second_summary = asyncio.run(run_collection_once(settings))

    assert first_summary.processed_accounts == 1
    assert second_summary.processed_accounts == 2
    state = read_json_file(data_dir / "runtime" / "state.json")
    assert set(state["accounts"]) == {"scheduler_blogger_0", "scheduler_blogger_1"}


async def completed_summary(_: ScheduledRunSettings | None = None) -> FetchCycleSummary:
    return FetchCycleSummary(
        processed_accounts=0,
        skipped_accounts=0,
        fetched_tweet_count=0,
        new_tweet_count=0,
        generated_report_count=0,
        daily_report_saved=False,
    )
