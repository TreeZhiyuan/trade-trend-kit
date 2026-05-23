"""Project-owned domain models.

The rest of the codebase should pass these models around instead of raw Twikit
objects, raw LLM responses, or unvalidated dictionaries. That keeps adapters
replaceable and gives application services one stable vocabulary.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DomainModel(BaseModel):
    """Base model with strict-ish defaults suitable for service boundaries."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AccountConfig(DomainModel):
    """One X account watched by the collector."""

    account: str = Field(min_length=1, description="X screen name without @.")
    display_name: str | None = None
    enabled: bool = True
    market: str = Field(min_length=1, description="Market dimension used in file names.")
    category: str = Field(min_length=1, description="Account category used in file names.")
    region: str | None = None
    tags: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=1)
    watch_symbols: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("account")
    @classmethod
    def normalize_account(cls, value: str) -> str:
        """Allow users to paste @handles while storing the canonical handle."""

        normalized = value.strip().lstrip("@")
        if not normalized:
            msg = "account cannot be empty"
            raise ValueError(msg)
        return normalized

    @field_validator("market", "category")
    @classmethod
    def normalize_grouping_field(cls, value: str) -> str:
        """Trim grouping fields because they are used in file names."""

        normalized = value.strip()
        if not normalized:
            msg = "grouping fields cannot be empty"
            raise ValueError(msg)
        return normalized

    @property
    def file_key(self) -> str:
        """Stable logical key used by storage adapters for per-account files."""

        return f"{self.market}_{self.category}_{self.account}"


class RuntimeConfig(DomainModel):
    """Validated contents of config/x.json."""

    timezone: str = "Asia/Shanghai"
    fetch_interval_minutes: int = Field(default=15, ge=1)
    tweet_limit: int = Field(default=10, ge=1, le=100)
    analysis_language: str = "zh-CN"
    preserve_english_summary: bool = True
    accounts: list[AccountConfig] = Field(default_factory=list)


class TweetMetrics(DomainModel):
    """Engagement metrics copied from X when available."""

    reply_count: int | None = None
    retweet_count: int | None = None
    favorite_count: int | None = None
    view_count: int | None = None


class AccountMeta(DomainModel):
    """Account classification copied onto each normalized tweet."""

    market: str
    category: str
    region: str | None = None
    tags: list[str] = Field(default_factory=list)
    watch_symbols: list[str] = Field(default_factory=list)

    @classmethod
    def from_account_config(cls, account: AccountConfig) -> "AccountMeta":
        """Create tweet metadata from the account config active during fetch."""

        return cls(
            market=account.market,
            category=account.category,
            region=account.region,
            tags=list(account.tags),
            watch_symbols=list(account.watch_symbols),
        )


class XUser(DomainModel):
    """Minimal X user details needed by downstream modules."""

    user_id: str
    account: str
    display_name: str | None = None


class RawTweet(DomainModel):
    """Boundary model for raw tweet data captured from an X adapter."""

    tweet_id: str
    user_id: str
    account: str
    payload: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime


class RawTweetBatch(DomainModel):
    """Raw fetch result saved for auditability before normalization."""

    account: AccountConfig
    user: XUser
    tweets: list[RawTweet]
    fetched_at: datetime


class NormalizedTweet(DomainModel):
    """Project-owned tweet shape used for analysis and reports."""

    tweet_id: str
    account: str
    display_name: str | None = None
    user_id: str
    created_at: datetime
    text: str
    english_summary: str | None = None
    lang: str | None = None
    url: str | None = None
    metrics: TweetMetrics = Field(default_factory=TweetMetrics)
    account_meta: AccountMeta
    fetched_at: datetime


class FetchResult(DomainModel):
    """Normalized output from any X post client implementation."""

    account: AccountConfig
    user: XUser
    raw_batch: RawTweetBatch
    normalized_tweets: list[NormalizedTweet]


class AccountRuntimeState(DomainModel):
    """Incremental processing state for one watched account."""

    user_id: str | None = None
    last_fetch_at: datetime | None = None
    last_success_at: datetime | None = None
    seen_tweet_ids: list[str] = Field(default_factory=list)
    analyzed_tweet_ids: list[str] = Field(default_factory=list)
    last_error: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)


class RuntimeState(DomainModel):
    """State file root used to keep scheduled runs idempotent."""

    accounts: dict[str, AccountRuntimeState] = Field(default_factory=dict)


class EnglishSourceSummary(DomainModel):
    """Short English summary preserved for each analyzed source tweet."""

    tweet_id: str
    summary: str


class StockWatchItem(DomainModel):
    """One symbol-level reference extracted from source tweets."""

    symbol: str
    direction: str
    reason: str
    confidence: Literal["low", "medium", "high"] = "medium"
    risk: str | None = None


class ChineseAccountReport(DomainModel):
    """Chinese analysis generated for newly collected tweets from one account."""

    summary: str
    market_direction: str
    key_themes: list[str] = Field(default_factory=list)
    mentioned_symbols: list[str] = Field(default_factory=list)
    stock_watchlist: list[StockWatchItem] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class AccountIncrementalReport(DomainModel):
    """Report generated from one account's newly discovered tweets."""

    report_id: str
    date: str
    account: str
    market: str
    category: str
    new_tweet_count: int = Field(ge=0)
    source_tweet_ids: list[str] = Field(default_factory=list)
    english_source_summaries: list[EnglishSourceSummary] = Field(default_factory=list)
    chinese_report: ChineseAccountReport
    created_at: datetime


class DailyCandidateSymbol(DomainModel):
    """Symbol-level idea prepared for daily report and future push services."""

    symbol: str
    market: str
    direction: str
    reason: str
    confidence: Literal["low", "medium", "high"] = "medium"
    risks: list[str] = Field(default_factory=list)


class DailyReport(DomainModel):
    """Daily aggregation of all account-level incremental reports."""

    date: str
    timezone: str
    report_count: int = Field(ge=0)
    source_accounts: list[str] = Field(default_factory=list)
    source_tweet_ids: list[str] = Field(default_factory=list)
    market_overview: str
    consensus_themes: list[str] = Field(default_factory=list)
    conflicting_views: list[str] = Field(default_factory=list)
    candidate_symbols: list[DailyCandidateSymbol] = Field(default_factory=list)
    risk_events: list[str] = Field(default_factory=list)
    disclaimer: str = "本报告由公开信息自动整理，仅供研究参考，不构成投资建议。"
    updated_at: datetime


class PublishResult(DomainModel):
    """Result returned by future report publishers."""

    channel: str
    success: bool
    message: str | None = None
    external_id: str | None = None
