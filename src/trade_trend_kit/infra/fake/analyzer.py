"""Deterministic fake analyzer for validating the report pipeline.

This adapter intentionally produces simple Chinese reports without calling a
model. The shape mirrors the real LLM adapter output so storage and aggregation
can be reviewed before API keys or prompt quality become variables.
"""

from __future__ import annotations

import re
from datetime import datetime

from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountIncrementalReport,
    ChineseAccountReport,
    EnglishSourceSummary,
    NormalizedTweet,
    StockWatchItem,
)
from trade_trend_kit.domain.ports import TweetAnalyzer
from trade_trend_kit.utils.time import DEFAULT_TIMEZONE, date_key, now_in_timezone

SYMBOL_PATTERN = re.compile(r"\b[A-Z]{1,5}\b")


class FakeTweetAnalyzer(TweetAnalyzer):
    """Create a predictable account report from newly discovered tweets."""

    def __init__(
        self,
        timezone: str = DEFAULT_TIMEZONE,
        fixed_now: datetime | None = None,
    ) -> None:
        self.timezone = timezone
        self.fixed_now = fixed_now

    async def analyze_account_tweets(
        self,
        account: AccountConfig,
        tweets: list[NormalizedTweet],
    ) -> AccountIncrementalReport:
        """Analyze only the tweets selected by the application service."""

        created_at = self.fixed_now or now_in_timezone(self.timezone)
        mentioned_symbols = _extract_symbols(tweets, account.watch_symbols)
        market_direction = _infer_direction(tweets)
        source_tweet_ids = [tweet.tweet_id for tweet in tweets]

        english_summaries = [
            EnglishSourceSummary(
                tweet_id=tweet.tweet_id,
                summary=tweet.english_summary or tweet.text[:160],
            )
            for tweet in tweets
        ]
        stock_watchlist = [
            StockWatchItem(
                symbol=symbol,
                direction=market_direction,
                reason=f"fake 分析：@{account.account} 在新增推文中提及 {symbol}。",
                confidence="medium",
                risk="真实接入前该结论仅用于流水线验证。",
            )
            for symbol in mentioned_symbols[:5]
        ]

        chinese_report = ChineseAccountReport(
            summary=(
                f"fake 分析：@{account.account} 本轮新增 {len(tweets)} 条推文，"
                f"主要围绕 {account.market}/{account.category} 展开。"
            ),
            market_direction=market_direction,
            key_themes=_extract_themes(account, tweets),
            mentioned_symbols=mentioned_symbols,
            stock_watchlist=stock_watchlist,
            risk_notes=["fake 结果仅验证端到端链路，不构成投资建议。"],
        )

        return AccountIncrementalReport(
            report_id=_build_report_id(account, source_tweet_ids, created_at),
            date=date_key(created_at, self.timezone),
            account=account.account,
            market=account.market,
            category=account.category,
            new_tweet_count=len(tweets),
            source_tweet_ids=source_tweet_ids,
            english_source_summaries=english_summaries,
            chinese_report=chinese_report,
            created_at=created_at,
        )


def _extract_symbols(
    tweets: list[NormalizedTweet],
    preferred_symbols: list[str],
) -> list[str]:
    """Extract likely symbols and keep configured watch symbols first."""

    discovered: list[str] = []
    for tweet in tweets:
        discovered.extend(SYMBOL_PATTERN.findall(tweet.text))

    preferred = [symbol.upper() for symbol in preferred_symbols]
    ignored = {"US", "X", "ETF", "AI"}
    candidates = [symbol for symbol in [*preferred, *discovered] if symbol not in ignored]
    return list(dict.fromkeys(candidates))


def _extract_themes(account: AccountConfig, tweets: list[NormalizedTweet]) -> list[str]:
    """Build simple report themes from account metadata and tweet volume."""

    themes = [*account.tags[:3], account.category]
    if tweets:
        themes.append("新增推文")
    return list(dict.fromkeys(theme for theme in themes if theme))


def _infer_direction(tweets: list[NormalizedTweet]) -> str:
    """Infer a coarse Chinese direction from synthetic tweet language."""

    cautious_count = sum("cautious" in tweet.text.lower() for tweet in tweets)
    constructive_count = sum("constructive" in tweet.text.lower() for tweet in tweets)
    if constructive_count > cautious_count:
        return "偏多"
    if cautious_count > constructive_count:
        return "偏谨慎"
    return "中性"


def _build_report_id(
    account: AccountConfig,
    source_tweet_ids: list[str],
    created_at: datetime,
) -> str:
    """Create an idempotent report ID for the same account and source tweets."""

    tweet_part = "-".join(source_tweet_ids[:3]) or "empty"
    timestamp = created_at.strftime("%Y%m%d%H%M%S")
    return f"{timestamp}_{account.market}_{account.category}_{account.account}_{tweet_part}"
