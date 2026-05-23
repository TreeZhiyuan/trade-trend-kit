from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from trade_trend_kit.domain.errors import XClientError
from trade_trend_kit.domain.models import AccountConfig, XUser
from trade_trend_kit.infra.x.normalizer import (
    XRawPost,
    build_raw_tweets,
    normalize_tweet_datetime,
    normalize_tweet_text,
    normalize_x_posts,
    twikit_tweet_to_raw_post,
)

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def make_account() -> AccountConfig:
    return AccountConfig(
        account="@macro_blogger",
        display_name="Macro Blogger",
        market="US_STOCK",
        category="macro",
        watch_symbols=["SPY"],
    )


def make_user() -> XUser:
    return XUser(user_id="u-1", account="macro_blogger", display_name="Macro Blogger")


def fixed_time() -> datetime:
    return datetime(2026, 5, 23, 10, 30, tzinfo=PROJECT_TZ)


def test_normalize_tweet_text_collapses_whitespace() -> None:
    assert normalize_tweet_text(" Fed\n\n liquidity\t  watch ") == "Fed liquidity watch"


def test_normalize_tweet_datetime_converts_to_project_timezone() -> None:
    value = normalize_tweet_datetime("2026-05-23T01:30:00+00:00", "Asia/Shanghai")

    assert value == datetime(2026, 5, 23, 9, 30, tzinfo=PROJECT_TZ)


def test_normalize_x_posts_dedupes_and_fills_url_metrics_and_summary() -> None:
    account = make_account()
    user = make_user()
    posts = [
        XRawPost(
            tweet_id="t1",
            text=" SPY\nliquidity ",
            created_at="2026-05-23T01:30:00+00:00",
            reply_count="1",
            retweet_count="2",
            favorite_count="3",
            view_count="4",
        ),
        XRawPost(tweet_id="t1", text="duplicate"),
    ]

    tweets = normalize_x_posts(
        posts,
        account=account,
        user=user,
        fetched_at=fixed_time(),
        timezone="Asia/Shanghai",
        english_summary_prefix="Fake summary for",
    )

    assert len(tweets) == 1
    assert tweets[0].text == "SPY liquidity"
    assert tweets[0].url == "https://x.com/macro_blogger/status/t1"
    assert tweets[0].metrics.favorite_count == 3
    assert tweets[0].english_summary == "Fake summary for @macro_blogger: SPY liquidity"
    assert tweets[0].account_meta.watch_symbols == ["SPY"]


def test_build_raw_tweets_uses_existing_payload() -> None:
    account = make_account()
    user = make_user()

    raw_tweets = build_raw_tweets(
        [XRawPost(tweet_id="t1", text="hello", payload={"source": "fake"})],
        account=account,
        user=user,
        fetched_at=fixed_time(),
    )

    assert raw_tweets[0].payload == {"source": "fake"}


def test_twikit_tweet_to_raw_post_prefers_full_text_and_payloads_datetime() -> None:
    tweet = SimpleNamespace(
        id="t1",
        text="short",
        full_text="full text",
        created_at_datetime=datetime(2026, 5, 23, 9, 0, tzinfo=PROJECT_TZ),
        lang="en",
    )

    post = twikit_tweet_to_raw_post(tweet)

    assert post.text == "full text"
    assert post.payload is not None
    assert post.payload["created_at_datetime"] == "2026-05-23T09:00:00+08:00"


def test_twikit_tweet_to_raw_post_requires_tweet_id() -> None:
    with pytest.raises(XClientError):
        twikit_tweet_to_raw_post(SimpleNamespace(text="missing id"))
