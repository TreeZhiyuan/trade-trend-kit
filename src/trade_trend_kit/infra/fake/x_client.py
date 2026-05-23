"""Deterministic fake X client for local end-to-end development.

The fake client implements the same port as the future Twikit adapter. It
generates stable tweet IDs from account metadata so repeated runs exercise the
incremental analysis path without hitting the network.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountMeta,
    FetchResult,
    NormalizedTweet,
    RawTweet,
    RawTweetBatch,
    TweetMetrics,
    XUser,
)
from trade_trend_kit.domain.ports import XPostClient
from trade_trend_kit.utils.time import DEFAULT_TIMEZONE, now_in_timezone


class FakeXPostClient(XPostClient):
    """Generate predictable finance-flavoured tweets for one account."""

    def __init__(
        self,
        timezone: str = DEFAULT_TIMEZONE,
        seed: str = "trade-trend-kit",
        fixed_now: datetime | None = None,
    ) -> None:
        self.timezone = timezone
        self.seed = seed
        self.fixed_now = fixed_now

    async def fetch_latest_posts(self, account: AccountConfig, limit: int) -> FetchResult:
        """Return a stable synthetic result that looks like a real adapter output."""

        fetched_at = self.fixed_now or now_in_timezone(self.timezone)
        user = XUser(
            user_id=_stable_id("user", account.account),
            account=account.account,
            display_name=account.display_name or account.account,
        )
        raw_tweets: list[RawTweet] = []
        normalized_tweets: list[NormalizedTweet] = []

        for index in range(limit):
            tweet_id = _stable_id(
                self.seed,
                account.market,
                account.category,
                account.account,
                index,
            )
            created_at = fetched_at - timedelta(minutes=index * 7)
            text = _fake_tweet_text(account, index)
            url = f"https://x.com/{account.account}/status/{tweet_id}"

            raw_tweets.append(
                RawTweet(
                    tweet_id=tweet_id,
                    user_id=user.user_id,
                    account=account.account,
                    payload={
                        "id": tweet_id,
                        "text": text,
                        "created_at": created_at.astimezone(UTC).isoformat(),
                        "url": url,
                        "source": "fake",
                    },
                    fetched_at=fetched_at,
                )
            )
            normalized_tweets.append(
                NormalizedTweet(
                    tweet_id=tweet_id,
                    account=account.account,
                    display_name=user.display_name,
                    user_id=user.user_id,
                    created_at=created_at,
                    text=text,
                    english_summary=f"Fake summary for @{account.account}: {text[:96]}",
                    lang="en",
                    url=url,
                    metrics=TweetMetrics(
                        reply_count=index,
                        retweet_count=index * 2,
                        favorite_count=10 + index * 3,
                        view_count=1_000 + index * 137,
                    ),
                    account_meta=AccountMeta.from_account_config(account),
                    fetched_at=fetched_at,
                )
            )

        raw_batch = RawTweetBatch(
            account=account,
            user=user,
            tweets=raw_tweets,
            fetched_at=fetched_at,
        )
        return FetchResult(
            account=account,
            user=user,
            raw_batch=raw_batch,
            normalized_tweets=normalized_tweets,
        )


def _fake_tweet_text(account: AccountConfig, index: int) -> str:
    """Create repeatable tweet text containing symbols and market language."""

    symbols = account.watch_symbols or ["SPY", "QQQ", "NVDA", "AAPL", "MSFT"]
    symbol = symbols[index % len(symbols)]
    direction = "constructive" if index % 3 != 1 else "cautious"
    theme = account.tags[index % len(account.tags)] if account.tags else account.category
    return (
        f"{account.market} {theme}: staying {direction} on {symbol}. "
        "Watching liquidity, earnings revisions, and policy headlines for confirmation."
    )


def _stable_id(*parts: object) -> str:
    """Build a short deterministic ID for fake tweets and users."""

    payload = "|".join(str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:18]
