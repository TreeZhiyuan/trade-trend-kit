"""Fetch-and-analyze job orchestration.

The application layer owns the business flow while concrete adapters handle
SDKs, files, or network calls. Keeping the cycle here lets `fetch-once`, the
future scheduler, and tests execute the same path.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter

from trade_trend_kit.app.incremental import (
    account_state_key,
    build_failure_account_state,
    build_success_account_state,
    select_new_tweets,
)
from trade_trend_kit.app.report_job import build_daily_report
from trade_trend_kit.domain.models import AccountRuntimeState, RuntimeConfig
from trade_trend_kit.domain.ports import (
    ReportRepository,
    StateRepository,
    TweetAnalyzer,
    TweetRepository,
    XPostClient,
)
from trade_trend_kit.utils.time import now_in_timezone

LOGGER = logging.getLogger(__name__)


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

        cycle_started_at = perf_counter()
        state = await self.state_repository.load()
        enabled_accounts = sorted(
            (account for account in config.accounts if account.enabled),
            key=lambda account: (account.priority, account.account.lower()),
        )
        skipped_accounts = len(config.accounts) - len(enabled_accounts)
        LOGGER.info(
            "Fetch cycle started: enabled_accounts=%s skipped_accounts=%s "
            "tweet_limit=%s timezone=%s",
            len(enabled_accounts),
            skipped_accounts,
            config.tweet_limit,
            config.timezone,
        )

        account_summaries: list[AccountCycleSummary] = []
        generated_reports = []
        fetched_tweet_count = 0
        new_tweet_count = 0

        for account in enabled_accounts:
            state_key = account_state_key(account)
            account_state = state.accounts.get(state_key, AccountRuntimeState())
            fetched_at = self.clock(config.timezone)

            try:
                LOGGER.info(
                    "Account fetch started: account=%s market=%s category=%s limit=%s",
                    account.account,
                    account.market,
                    account.category,
                    config.tweet_limit,
                )
                fetch_result = await self.x_client.fetch_latest_posts(
                    account=account,
                    limit=config.tweet_limit,
                )
                fetched_tweets = fetch_result.normalized_tweets
                selection = select_new_tweets(fetched_tweets, account_state)
                LOGGER.info(
                    "Account fetch finished: account=%s fetched=%s new=%s",
                    account.account,
                    len(fetched_tweets),
                    len(selection.new_tweets),
                )

                await self.tweet_repository.save_raw(fetch_result.raw_batch)
                await self.tweet_repository.save_normalized(fetched_tweets)

                report_id = None
                if selection.new_tweets:
                    LOGGER.info(
                        "Account analysis started: account=%s new_tweets=%s",
                        account.account,
                        len(selection.new_tweets),
                    )
                    report = await self.analyzer.analyze_account_tweets(
                        account,
                        selection.new_tweets,
                    )
                    await self.report_repository.save_account_report(report)
                    generated_reports.append(report)
                    report_id = report.report_id
                    LOGGER.info(
                        "Account analysis finished: account=%s report_id=%s",
                        account.account,
                        report_id,
                    )
                else:
                    LOGGER.info(
                        "Account analysis skipped: account=%s reason=no_new_tweets",
                        account.account,
                    )

                fetched_tweet_count += len(fetched_tweets)
                new_tweet_count += len(selection.new_tweets)
                state.accounts[state_key] = build_success_account_state(
                    previous=account_state,
                    user_id=fetch_result.user.user_id,
                    fetched_at=fetch_result.raw_batch.fetched_at,
                    success_at=fetched_at,
                    fetched_tweet_ids=selection.fetched_tweet_ids,
                    analyzed_tweet_ids=selection.new_tweet_ids,
                )
                account_summaries.append(
                    AccountCycleSummary(
                        account=account.account,
                        fetched_tweet_count=len(fetched_tweets),
                        new_tweet_count=len(selection.new_tweets),
                        report_id=report_id,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - keep one bad account from blocking others.
                LOGGER.exception("Account cycle failed: account=%s", account.account)
                state.accounts[state_key] = build_failure_account_state(
                    previous=account_state,
                    attempted_at=fetched_at,
                    error=exc,
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
            LOGGER.info(
                "Daily report saved: date=%s report_count=%s",
                daily_report.date,
                daily_report.report_count,
            )
        else:
            LOGGER.info("Daily report skipped: reason=no_account_reports")

        await self.state_repository.save(state)
        duration_ms = int((perf_counter() - cycle_started_at) * 1000)
        LOGGER.info(
            "Fetch cycle finished: processed=%s skipped=%s fetched=%s new=%s "
            "reports=%s daily_report_saved=%s duration_ms=%s",
            len(enabled_accounts),
            skipped_accounts,
            fetched_tweet_count,
            new_tweet_count,
            len(generated_reports),
            daily_report_saved,
            duration_ms,
        )

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
