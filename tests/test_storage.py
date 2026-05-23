from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountIncrementalReport,
    AccountMeta,
    AccountRuntimeState,
    ChineseAccountReport,
    DailyReport,
    DailyCandidateSymbol,
    EnglishSourceSummary,
    NormalizedTweet,
    RawTweet,
    RawTweetBatch,
    RuntimeState,
    StockWatchItem,
    TweetMetrics,
    XUser,
)
from trade_trend_kit.infra.storage.json_report_store import JsonReportRepository
from trade_trend_kit.infra.storage.json_state_store import JsonStateRepository
from trade_trend_kit.infra.storage.json_tweet_store import JsonTweetRepository
from trade_trend_kit.utils.filenames import (
    build_report_file_stem,
    normalize_filename_part,
)
from trade_trend_kit.utils.json_io import read_json_file, write_json_file
from trade_trend_kit.utils.time import date_key

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def fixed_time(hour: int = 10) -> datetime:
    return datetime(2026, 5, 23, hour, 0, tzinfo=PROJECT_TZ)


def make_account() -> AccountConfig:
    return AccountConfig(account="@ExampleUser", market="US_STOCK", category="macro")


def make_raw_batch(*tweet_ids: str) -> RawTweetBatch:
    account = make_account()
    user = XUser(user_id="u-1", account=account.account, display_name="Example User")
    tweets = [
        RawTweet(
            tweet_id=tweet_id,
            user_id=user.user_id,
            account=account.account,
            payload={"text": f"raw {tweet_id}"},
            fetched_at=fixed_time(),
        )
        for tweet_id in tweet_ids
    ]
    return RawTweetBatch(account=account, user=user, tweets=tweets, fetched_at=fixed_time())


def make_normalized_tweet(tweet_id: str) -> NormalizedTweet:
    account = make_account()
    return NormalizedTweet(
        tweet_id=tweet_id,
        account=account.account,
        display_name="Example User",
        user_id="u-1",
        created_at=fixed_time(),
        text=f"normalized {tweet_id}",
        english_summary=None,
        lang="en",
        url=f"https://x.com/{account.account}/status/{tweet_id}",
        metrics=TweetMetrics(reply_count=1),
        account_meta=AccountMeta.from_account_config(account),
        fetched_at=fixed_time(),
    )


def make_account_report(report_id: str = "report-1") -> AccountIncrementalReport:
    account = make_account()
    return AccountIncrementalReport(
        report_id=report_id,
        date="2026-05-23",
        account=account.account,
        market=account.market,
        category=account.category,
        new_tweet_count=1,
        source_tweet_ids=["1"],
        english_source_summaries=[
            EnglishSourceSummary(tweet_id="1", summary="Rates remain important.")
        ],
        chinese_report=ChineseAccountReport(
            summary="summary",
            market_direction="neutral",
            key_themes=["rates"],
            stock_watchlist=[
                StockWatchItem(
                    symbol="SPY",
                    direction="关注",
                    reason="macro signal",
                    risk="single source",
                )
            ],
            risk_notes=["risk note"],
        ),
        created_at=fixed_time(),
    )


def make_daily_report(updated_at: datetime | None = None) -> DailyReport:
    return DailyReport(
        date="2026-05-23",
        timezone="Asia/Shanghai",
        report_count=1,
        source_accounts=["ExampleUser"],
        source_tweet_ids=["1"],
        market_overview="neutral",
        consensus_themes=["rates"],
        candidate_symbols=[
            DailyCandidateSymbol(
                symbol="SPY",
                market="US_STOCK",
                direction="关注",
                reason="macro signal",
            )
        ],
        risk_events=["FOMC"],
        updated_at=updated_at or fixed_time(),
    )


def test_filename_and_date_helpers_are_storage_safe() -> None:
    assert normalize_filename_part(" US/STOCK Macro ") == "us_stock_macro"
    assert build_report_file_stem("US_STOCK", "macro", "@Example.User") == (
        "us_stock_macro_example.user"
    )

    utc_time = datetime(2026, 5, 22, 16, 30, tzinfo=ZoneInfo("UTC"))
    assert date_key(utc_time, "Asia/Shanghai") == "2026-05-23"


def test_write_json_file_creates_parent_dirs_and_removes_temp_file(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "sample.json"

    write_json_file(path, {"value": 1})

    assert read_json_file(path) == {"value": 1}
    assert not path.with_name(f"{path.name}.tmp").exists()


def test_json_state_repository_round_trips_runtime_state(tmp_path: Path) -> None:
    repo = JsonStateRepository(tmp_path / "runtime" / "state.json")
    state = RuntimeState(
        accounts={
            "ExampleUser": AccountRuntimeState(
                user_id="u-1",
                seen_tweet_ids=["1"],
                analyzed_tweet_ids=["1"],
            )
        }
    )

    asyncio.run(repo.save(state))
    loaded = asyncio.run(repo.load())

    assert loaded.accounts["ExampleUser"].user_id == "u-1"
    assert loaded.accounts["ExampleUser"].seen_tweet_ids == ["1"]


def test_json_tweet_repository_merges_daily_raw_and_normalized_tweets(
    tmp_path: Path,
) -> None:
    repo = JsonTweetRepository(
        raw_dir=tmp_path / "raw_tweets",
        normalized_dir=tmp_path / "normalized_tweets",
        timezone="Asia/Shanghai",
    )

    asyncio.run(repo.save_raw(make_raw_batch("1")))
    asyncio.run(repo.save_raw(make_raw_batch("1", "2")))
    asyncio.run(repo.save_normalized([make_normalized_tweet("1")]))
    asyncio.run(repo.save_normalized([make_normalized_tweet("2")]))

    stem = "us_stock_macro_exampleuser"
    raw_payload = read_json_file(tmp_path / "raw_tweets" / "2026-05-23" / f"{stem}.json")
    normalized_payload = read_json_file(
        tmp_path / "normalized_tweets" / "2026-05-23" / f"{stem}.json"
    )

    assert raw_payload["tweet_count"] == 2
    assert normalized_payload["tweet_count"] == 2
    assert {tweet["tweet_id"] for tweet in normalized_payload["tweets"]} == {"1", "2"}


def test_json_report_repository_saves_latest_history_and_markdown_archives(
    tmp_path: Path,
) -> None:
    repo = JsonReportRepository(tmp_path / "reports")
    account_report = make_account_report()
    daily_report = make_daily_report()

    asyncio.run(repo.save_account_report(account_report))
    asyncio.run(repo.save_account_report(account_report))
    asyncio.run(repo.save_daily_report(daily_report))
    asyncio.run(repo.save_daily_report(daily_report))

    stem = "us_stock_macro_exampleuser"
    account_dir = tmp_path / "reports" / "2026-05-23" / "accounts"
    account_latest = read_json_file(account_dir / f"{stem}.latest.json")
    account_history = read_json_file(account_dir / f"{stem}.history.json")
    account_latest_markdown = (account_dir / f"{stem}.latest.md").read_text(encoding="utf-8")
    account_archive_dir = account_dir / "archive"
    daily_latest = read_json_file(tmp_path / "reports" / "2026-05-23" / "daily_report.json")
    daily_latest_markdown = (
        tmp_path / "reports" / "2026-05-23" / "daily_report.md"
    ).read_text(encoding="utf-8")
    daily_history = read_json_file(
        tmp_path / "reports" / "2026-05-23" / "daily_report.history.json"
    )
    daily_archive_dir = tmp_path / "reports" / "2026-05-23" / "archive"

    assert account_latest["report_id"] == "report-1"
    assert len(account_history) == 1
    assert account_latest_markdown.startswith("# US_STOCK / macro / @ExampleUser")
    assert "## 英文原文摘要" in account_latest_markdown
    assert len(list(account_archive_dir.glob("*.json"))) == 1
    assert len(list(account_archive_dir.glob("*.md"))) == 1
    assert daily_latest["date"] == "2026-05-23"
    assert daily_latest_markdown.startswith("# 2026-05-23 投资方向参考报告")
    assert "## 候选标的" in daily_latest_markdown
    assert len(daily_history) == 1
    assert len(list(daily_archive_dir.glob("*.json"))) == 1
    assert len(list(daily_archive_dir.glob("*.md"))) == 1
