"""Replaceable domain ports implemented by infrastructure adapters.

Application services should depend on these protocols instead of concrete SDKs
or local file implementations. This is the seam that lets us replace Twikit,
JSON storage, LLM providers, and publishers independently.
"""

from __future__ import annotations

from typing import Protocol

from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountIncrementalReport,
    DailyReport,
    FetchResult,
    NormalizedTweet,
    PublishPayload,
    PublishResult,
    RawTweetBatch,
    RuntimeState,
)


class XPostClient(Protocol):
    """Port for fetching the latest posts from X or an X-compatible source."""

    async def fetch_latest_posts(self, account: AccountConfig, limit: int) -> FetchResult:
        """Fetch and normalize the latest posts for one account."""
        ...


class TweetRepository(Protocol):
    """Port for persisting raw and normalized tweet data."""

    async def save_raw(self, batch: RawTweetBatch) -> None:
        """Persist raw adapter output for auditability."""
        ...

    async def save_normalized(self, tweets: list[NormalizedTweet]) -> None:
        """Persist project-owned tweet models used by analysis."""
        ...


class StateRepository(Protocol):
    """Port for loading and saving incremental runtime state."""

    async def load(self) -> RuntimeState:
        """Load scheduler state, returning an empty state if none exists."""
        ...

    async def save(self, state: RuntimeState) -> None:
        """Persist scheduler state after successful account processing."""
        ...


class TweetAnalyzer(Protocol):
    """Port for turning newly collected tweets into account-level analysis."""

    async def analyze_account_tweets(
        self,
        account: AccountConfig,
        tweets: list[NormalizedTweet],
    ) -> AccountIncrementalReport:
        """Analyze only the tweets selected as new by application services."""
        ...


class ReportRepository(Protocol):
    """Port for persisting generated account and daily reports."""

    async def save_account_report(self, report: AccountIncrementalReport) -> None:
        """Persist one incremental account report."""
        ...

    async def save_daily_report(self, report: DailyReport) -> None:
        """Persist the current daily aggregate report."""
        ...


class ReportPublisher(Protocol):
    """Port for future delivery channels such as social platforms or apps."""

    async def publish_daily_report(self, payload: PublishPayload) -> PublishResult:
        """Publish a prepared daily report payload to one delivery channel."""
        ...
