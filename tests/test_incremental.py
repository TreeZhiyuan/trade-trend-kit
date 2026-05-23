from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from trade_trend_kit.app.incremental import (
    account_state_key,
    build_failure_account_state,
    build_success_account_state,
    merge_tweet_ids,
    select_new_tweets,
)
from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountMeta,
    AccountRuntimeState,
    NormalizedTweet,
)

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def fixed_time(hour: int = 10) -> datetime:
    return datetime(2026, 5, 23, hour, 0, tzinfo=PROJECT_TZ)


def make_account() -> AccountConfig:
    return AccountConfig(account="@MacroBlogger", market="US_STOCK", category="macro")


def make_tweet(tweet_id: str) -> NormalizedTweet:
    account = make_account()
    return NormalizedTweet(
        tweet_id=tweet_id,
        account=account.account,
        user_id="u-1",
        created_at=fixed_time(),
        text=f"tweet {tweet_id}",
        account_meta=AccountMeta.from_account_config(account),
        fetched_at=fixed_time(),
    )


def test_account_state_key_is_case_stable() -> None:
    assert account_state_key(make_account()) == "macroblogger"


def test_select_new_tweets_skips_analyzed_and_duplicate_tweets() -> None:
    state = AccountRuntimeState(analyzed_tweet_ids=["1"])
    selection = select_new_tweets(
        tweets=[make_tweet("1"), make_tweet("2"), make_tweet("2"), make_tweet("3")],
        state=state,
    )

    assert selection.fetched_tweet_ids == ["1", "2", "3"]
    assert selection.new_tweet_ids == ["2", "3"]
    assert selection.skipped_tweet_ids == ["1", "2"]


def test_success_state_merges_seen_and_analyzed_ids_after_analysis() -> None:
    previous = AccountRuntimeState(
        user_id="old-user",
        seen_tweet_ids=["1"],
        analyzed_tweet_ids=["1"],
        last_error="previous error",
        consecutive_failures=2,
    )

    state = build_success_account_state(
        previous=previous,
        user_id="new-user",
        fetched_at=fixed_time(11),
        success_at=fixed_time(12),
        fetched_tweet_ids=["1", "2", "3"],
        analyzed_tweet_ids=["2"],
    )

    assert state.user_id == "new-user"
    assert state.seen_tweet_ids == ["1", "2", "3"]
    assert state.analyzed_tweet_ids == ["1", "2"]
    assert state.last_error is None
    assert state.consecutive_failures == 0


def test_failure_state_preserves_analysis_progress() -> None:
    previous = AccountRuntimeState(
        user_id="u-1",
        seen_tweet_ids=["1"],
        analyzed_tweet_ids=["1"],
        consecutive_failures=1,
    )

    state = build_failure_account_state(
        previous=previous,
        attempted_at=fixed_time(13),
        error=RuntimeError("llm timeout"),
    )

    assert state.last_fetch_at == fixed_time(13)
    assert state.seen_tweet_ids == ["1"]
    assert state.analyzed_tweet_ids == ["1"]
    assert state.last_error == "llm timeout"
    assert state.consecutive_failures == 2


def test_merge_tweet_ids_respects_state_size_limit() -> None:
    assert merge_tweet_ids(["1", "2"], ["2", "3"], max_items=2) == ["2", "3"]
