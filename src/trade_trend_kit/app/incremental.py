"""Incremental tweet analysis helpers.

This module keeps idempotency rules out of the orchestration flow. The job asks
which tweets are new, then records state only after analysis/report persistence
has succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountRuntimeState,
    NormalizedTweet,
)

MAX_TRACKED_TWEET_IDS = 5_000


@dataclass(frozen=True)
class IncrementalTweetSelection:
    """Tweets selected for analysis in one account cycle."""

    fetched_tweet_ids: list[str]
    new_tweets: list[NormalizedTweet]
    skipped_tweet_ids: list[str]

    @property
    def new_tweet_ids(self) -> list[str]:
        """Return the selected tweet IDs in analysis order."""

        return [tweet.tweet_id for tweet in self.new_tweets]


def account_state_key(account: AccountConfig) -> str:
    """Use a case-stable account key so config casing changes do not reset state."""

    return account.account.lower()


def select_new_tweets(
    tweets: list[NormalizedTweet],
    state: AccountRuntimeState,
) -> IncrementalTweetSelection:
    """Select tweets that have not already been analyzed for this account."""

    analyzed_ids = set(state.analyzed_tweet_ids)
    fetched_tweet_ids = _unique_tweet_ids(tweet.tweet_id for tweet in tweets)
    selected_tweets: list[NormalizedTweet] = []
    skipped_tweet_ids: list[str] = []
    selected_ids: set[str] = set()

    for tweet in tweets:
        if tweet.tweet_id in analyzed_ids:
            skipped_tweet_ids.append(tweet.tweet_id)
            continue
        if tweet.tweet_id in selected_ids:
            skipped_tweet_ids.append(tweet.tweet_id)
            continue
        selected_tweets.append(tweet)
        selected_ids.add(tweet.tweet_id)

    return IncrementalTweetSelection(
        fetched_tweet_ids=fetched_tweet_ids,
        new_tweets=selected_tweets,
        skipped_tweet_ids=_unique_tweet_ids(skipped_tweet_ids),
    )


def build_success_account_state(
    previous: AccountRuntimeState,
    user_id: str,
    fetched_at: datetime,
    success_at: datetime,
    fetched_tweet_ids: list[str],
    analyzed_tweet_ids: list[str],
) -> AccountRuntimeState:
    """Build account state after fetch, analysis, and report writes succeeded."""

    return AccountRuntimeState(
        user_id=user_id,
        last_fetch_at=fetched_at,
        last_success_at=success_at,
        seen_tweet_ids=merge_tweet_ids(previous.seen_tweet_ids, fetched_tweet_ids),
        analyzed_tweet_ids=merge_tweet_ids(previous.analyzed_tweet_ids, analyzed_tweet_ids),
        last_error=None,
        consecutive_failures=0,
    )


def build_failure_account_state(
    previous: AccountRuntimeState,
    attempted_at: datetime,
    error: Exception,
) -> AccountRuntimeState:
    """Build account state after a failed account cycle."""

    return AccountRuntimeState(
        user_id=previous.user_id,
        last_fetch_at=attempted_at,
        last_success_at=previous.last_success_at,
        seen_tweet_ids=previous.seen_tweet_ids,
        analyzed_tweet_ids=previous.analyzed_tweet_ids,
        last_error=str(error),
        consecutive_failures=previous.consecutive_failures + 1,
    )


def merge_tweet_ids(
    existing_ids: list[str],
    new_ids: list[str],
    max_items: int = MAX_TRACKED_TWEET_IDS,
) -> list[str]:
    """Merge tweet IDs while preserving first-seen order and bounding state size."""

    merged = _unique_tweet_ids([*existing_ids, *new_ids])
    if len(merged) <= max_items:
        return merged
    return merged[-max_items:]


def _unique_tweet_ids(tweet_ids) -> list[str]:
    """Return tweet IDs in first-seen order without duplicates."""

    return list(dict.fromkeys(str(tweet_id) for tweet_id in tweet_ids))
