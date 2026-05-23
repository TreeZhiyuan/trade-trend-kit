"""Fetch-and-analyze job orchestration.

The application layer owns the business flow while concrete adapters handle
SDKs, files, or network calls. Keeping the cycle here lets `fetch-once`, the
future scheduler, and tests execute the same path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from trade_trend_kit.app.report_job import build_daily_report
from trade_trend_kit.domain.models import AccountConfig, AccountRuntimeState, RuntimeConfig
from trade_trend_kit.domain.ports import (
    ReportRepository,
    StateRepository,
    TweetAnalyzer,
    TweetRepository,
    XPostClient,
)
from trade_trend_kit.utils.time import now_in_timezone

MAX_TRACKED_TWEET_IDS = 5_000


@dataclass(frozen=True)
class AccountCycleSummary:
    """Human-readable outcome for one account in a fetch cycle."""

    account: str
    fetched_tweet_count: int = 0
    new_tweet_count: int = 0
    report_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class FetchCycleSummary:
    """Aggregate result returned by one fetch-and-analyze cycle."""

    processed_accounts: int
    skipped_accounts: int
    fetched_tweet_count: int
    new_tweet_count: int
    generated_report_count: int
    daily_report_saved: bool
    account_summaries: list[AccountCycleSummary] = field(default_factory=list)


class FetchAndAnalyzeJob:
    """Coordinate fetching, local persistence, incremental analysis, and state."""

    def __init__(
        self,
        x_client: XPostClient,
        tweet_repository: TweetRepository,
        state_repository: StateRepository,
        analyzer: TweetAnalyzer,
        report_repository: ReportRepository,
        clock: Callable[[str], datetime] | None = None,
    ) -> None:
        self.x_client = x_client
        self.tweet_repository = tweet_repository
        self.state_repository = state_repository
        self.analyzer = analyzer
        self.report_repository = report_repository
        self.clock = clock or now_in_timezone

    async def run_once(self, config: RuntimeConfig) -> FetchCycleSummary:
        """Run one configured collection cycle and analyze only new tweets."""

        state = await self.state_repository.load()
        enabled_accounts = sorted(
            (account for account in config.accounts if account.enabled),
            key=lambda account: (account.priority, account.account.lower()),
        )
        skipped_accounts = len(config.accounts) - len(enabled_accounts)

        account_summaries: list[AccountCycleSummary] = []
        generated_reports = []
        fetched_tweet_count = 0
        new_tweet_count = 0

        for account in enabled_accounts:
            state_key = _state_key(account)
            account_state = state.accounts.get(state_key, AccountRuntimeState())
            fetched_at = self.clock(config.timezone)

            try:
                fetch_result = await self.x_client.fetch_latest_posts(
                    account=account,
                    limit=config.tweet_limit,
                )
                fetched_tweets = fetch_result.normalized_tweets
                fetched_tweet_ids = [tweet.tweet_id for tweet in fetched_tweets]
                already_analyzed_ids = set(account_state.analyzed_tweet_ids)
                new_tweets = [
                    tweet for tweet in fetched_tweets if tweet.tweet_id not in already_analyzed_ids
                ]

                await self.tweet_repository.save_raw(fetch_result.raw_batch)
                await self.tweet_repository.save_normalized(fetched_tweets)

                report_id = None
                if new_tweets:
                    report = await self.analyzer.analyze_account_tweets(account, new_tweets)
                    await self.report_repository.save_account_report(report)
                    generated_reports.append(report)
                    report_id = report.report_id

                fetched_tweet_count += len(fetched_tweets)
                new_tweet_count += len(new_tweets)
                state.accounts[state_key] = AccountRuntimeState(
                    user_id=fetch_result.user.user_id,
                    last_fetch_at=fetch_result.raw_batch.fetched_at,
                    last_success_at=fetched_at,
                    seen_tweet_ids=_merge_tweet_ids(
                        account_state.seen_tweet_ids,
                        fetched_tweet_ids,
                    ),
                    analyzed_tweet_ids=_merge_tweet_ids(
                        account_state.analyzed_tweet_ids,
                        [tweet.tweet_id for tweet in new_tweets],
                    ),
                    last_error=None,
                    consecutive_failures=0,
                )
                account_summaries.append(
                    AccountCycleSummary(
                        account=account.account,
                        fetched_tweet_count=len(fetched_tweets),
                        new_tweet_count=len(new_tweets),
                        report_id=report_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - keep one bad account from blocking others.
                state.accounts[state_key] = AccountRuntimeState(
                    user_id=account_state.user_id,
                    last_fetch_at=fetched_at,
                    last_success_at=account_state.last_success_at,
                    seen_tweet_ids=account_state.seen_tweet_ids,
                    analyzed_tweet_ids=account_state.analyzed_tweet_ids,
                    last_error=str(exc),
                    consecutive_failures=account_state.consecutive_failures + 1,
                )
                account_summaries.append(
                    AccountCycleSummary(account=account.account, error=str(exc))
                )

        daily_report_saved = False
        if generated_reports:
            daily_report = build_daily_report(
                reports=generated_reports,
                timezone=config.timezone,
                generated_at=self.clock(config.timezone),
            )
            await self.report_repository.save_daily_report(daily_report)
            daily_report_saved = True

        await self.state_repository.save(state)

        return FetchCycleSummary(
            processed_accounts=len(enabled_accounts),
            skipped_accounts=skipped_accounts,
            fetched_tweet_count=fetched_tweet_count,
            new_tweet_count=new_tweet_count,
            generated_report_count=len(generated_reports),
            daily_report_saved=daily_report_saved,
            account_summaries=account_summaries,
        )


def format_fetch_cycle_summary(summary: FetchCycleSummary) -> str:
    """Render a concise CLI summary without leaking adapter internals."""

    lines = [
        (
            "Fetch cycle complete: "
            f"processed={summary.processed_accounts}, "
            f"skipped={summary.skipped_accounts}, "
            f"fetched={summary.fetched_tweet_count}, "
            f"new={summary.new_tweet_count}, "
            f"reports={summary.generated_report_count}, "
            f"daily_report_saved={summary.daily_report_saved}"
        )
    ]
    for account_summary in summary.account_summaries:
        if account_summary.error:
            lines.append(f"- {account_summary.account}: failed: {account_summary.error}")
            continue
        lines.append(
            f"- {account_summary.account}: fetched={account_summary.fetched_tweet_count}, "
            f"new={account_summary.new_tweet_count}, report={account_summary.report_id or '-'}"
        )
    return "\n".join(lines)


def _state_key(account: AccountConfig) -> str:
    """Use a case-stable account key so config casing changes do not reset state."""

    return account.account.lower()


def _merge_tweet_ids(
    existing_ids: list[str],
    new_ids: list[str],
    max_items: int = MAX_TRACKED_TWEET_IDS,
) -> list[str]:
    """Merge tweet IDs while preserving first-seen order and bounding state size."""

    merged = list(dict.fromkeys([*existing_ids, *new_ids]))
    if len(merged) <= max_items:
        return merged
    return merged[-max_items:]
