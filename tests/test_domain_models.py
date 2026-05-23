from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountIncrementalReport,
    AccountMeta,
    ChineseAccountReport,
    NormalizedTweet,
    RuntimeState,
)


def test_account_config_normalizes_handle_and_builds_file_key() -> None:
    account = AccountConfig(
        account="@ExampleUser",
        market="US_STOCK",
        category="macro",
    )

    assert account.account == "ExampleUser"
    assert account.file_key == "US_STOCK_macro_ExampleUser"


def test_account_meta_is_copied_from_account_config() -> None:
    account = AccountConfig(
        account="example_user",
        market="US_STOCK",
        category="macro",
        region="US",
        tags=["fed"],
        watch_symbols=["SPY"],
    )

    meta = AccountMeta.from_account_config(account)

    assert meta.market == "US_STOCK"
    assert meta.category == "macro"
    assert meta.tags == ["fed"]
    assert meta.watch_symbols == ["SPY"]


def test_runtime_state_defaults_to_empty_account_map() -> None:
    state = RuntimeState()

    assert state.accounts == {}


def test_account_report_keeps_chinese_report_and_source_ids() -> None:
    report = AccountIncrementalReport(
        report_id="2026-05-23T10:00:00_example_user",
        date="2026-05-23",
        account="example_user",
        market="US_STOCK",
        category="macro",
        new_tweet_count=1,
        source_tweet_ids=["123"],
        chinese_report=ChineseAccountReport(
            summary="新增推文偏谨慎。",
            market_direction="中性",
        ),
        created_at=datetime(2026, 5, 23, 10, 0, tzinfo=UTC),
    )

    assert report.source_tweet_ids == ["123"]
    assert report.chinese_report.summary == "新增推文偏谨慎。"


def test_fake_analyzer_can_replace_real_llm_adapter() -> None:
    class FakeAnalyzer:
        async def analyze_account_tweets(
            self,
            account: AccountConfig,
            tweets: list[NormalizedTweet],
        ) -> AccountIncrementalReport:
            return AccountIncrementalReport(
                report_id="fake",
                date="2026-05-23",
                account=account.account,
                market=account.market,
                category=account.category,
                new_tweet_count=len(tweets),
                source_tweet_ids=[tweet.tweet_id for tweet in tweets],
                chinese_report=ChineseAccountReport(
                    summary="fake summary",
                    market_direction="中性",
                ),
                created_at=datetime(2026, 5, 23, 10, 0, tzinfo=UTC),
            )

    account = AccountConfig(account="example_user", market="US_STOCK", category="macro")
    analyzer = FakeAnalyzer()

    report = asyncio.run(analyzer.analyze_account_tweets(account, []))

    assert report.account == "example_user"
    assert report.new_tweet_count == 0
