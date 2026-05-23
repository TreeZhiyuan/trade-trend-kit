"""X tweet normalization shared by real and fake X adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trade_trend_kit.domain.errors import XClientError
from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountMeta,
    NormalizedTweet,
    RawTweet,
    TweetMetrics,
    XUser,
)
from trade_trend_kit.utils.time import DEFAULT_TIMEZONE, to_timezone

WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class XRawPost:
    """Provider-neutral X post shape before project normalization."""

    tweet_id: str
    text: str
    created_at: datetime | str | None = None
    lang: str | None = None
    url: str | None = None
    reply_count: int | str | None = None
    retweet_count: int | str | None = None
    favorite_count: int | str | None = None
    view_count: int | str | None = None
    payload: dict[str, Any] | None = None


def normalize_x_posts(
    posts: list[XRawPost],
    account: AccountConfig,
    user: XUser,
    fetched_at: datetime,
    timezone: str = DEFAULT_TIMEZONE,
    english_summary_prefix: str | None = None,
) -> list[NormalizedTweet]:
    """Normalize fetched X posts into project-owned tweet models."""

    normalized: list[NormalizedTweet] = []
    seen_ids: set[str] = set()
    for post in posts:
        tweet_id = _required_text(post.tweet_id, "Tweet id")
        if tweet_id in seen_ids:
            continue
        seen_ids.add(tweet_id)

        text = normalize_tweet_text(post.text)
        normalized.append(
            NormalizedTweet(
                tweet_id=tweet_id,
                account=account.account,
                display_name=user.display_name,
                user_id=user.user_id,
                created_at=normalize_tweet_datetime(post.created_at, timezone),
                text=text,
                english_summary=_build_english_summary(english_summary_prefix, account, text),
                lang=_optional_text(post.lang),
                url=normalize_tweet_url(post.url, account.account, tweet_id),
                metrics=TweetMetrics(
                    reply_count=_optional_int(post.reply_count),
                    retweet_count=_optional_int(post.retweet_count),
                    favorite_count=_optional_int(post.favorite_count),
                    view_count=_optional_int(post.view_count),
                ),
                account_meta=AccountMeta.from_account_config(account),
                fetched_at=fetched_at,
            )
        )
    return normalized


def build_raw_tweets(
    posts: list[XRawPost],
    account: AccountConfig,
    user: XUser,
    fetched_at: datetime,
) -> list[RawTweet]:
    """Build raw audit records from provider-neutral posts."""

    raw_tweets: list[RawTweet] = []
    seen_ids: set[str] = set()
    for post in posts:
        tweet_id = _required_text(post.tweet_id, "Tweet id")
        if tweet_id in seen_ids:
            continue
        seen_ids.add(tweet_id)
        raw_tweets.append(
            RawTweet(
                tweet_id=tweet_id,
                user_id=user.user_id,
                account=account.account,
                payload=post.payload or post_to_payload(post),
                fetched_at=fetched_at,
            )
        )
    return raw_tweets


def post_to_payload(post: XRawPost) -> dict[str, Any]:
    """Convert a provider-neutral post into JSON-serializable raw payload."""

    payload: dict[str, Any] = {
        "id": post.tweet_id,
        "text": post.text,
    }
    if post.created_at is not None:
        payload["created_at"] = (
            post.created_at.isoformat() if isinstance(post.created_at, datetime) else post.created_at
        )
    for name in ("lang", "url", "reply_count", "retweet_count", "favorite_count", "view_count"):
        value = getattr(post, name)
        if value is not None:
            payload[name] = value
    return payload


def normalize_tweet_text(value: str | None) -> str:
    """Trim and collapse whitespace in tweet text."""

    if value is None:
        return ""
    return WHITESPACE_PATTERN.sub(" ", str(value)).strip()


def normalize_tweet_datetime(
    value: datetime | str | None,
    timezone: str = DEFAULT_TIMEZONE,
) -> datetime:
    """Convert tweet timestamps into the configured project timezone."""

    if isinstance(value, datetime):
        return to_timezone(value, timezone)
    if isinstance(value, str) and value.strip():
        try:
            return to_timezone(datetime.fromisoformat(value.strip().replace("Z", "+00:00")), timezone)
        except ValueError as exc:
            raise XClientError(f"Invalid tweet created_at value: {value}") from exc
    return to_timezone(datetime.now().astimezone(), timezone)


def normalize_tweet_url(value: str | None, account: str, tweet_id: str) -> str:
    """Return a stable tweet URL even when the provider does not include one."""

    url = _optional_text(value)
    if url:
        return url
    return f"https://x.com/{account}/status/{tweet_id}"


def twikit_tweet_to_raw_post(tweet: Any) -> XRawPost:
    """Convert a Twikit Tweet-like object into provider-neutral post data."""

    tweet_id = _required_text(_obj_value(tweet, "id"), "Tweet id")
    text = normalize_tweet_text(_obj_value(tweet, "full_text") or _obj_value(tweet, "text"))
    return XRawPost(
        tweet_id=tweet_id,
        text=text,
        created_at=_obj_value(tweet, "created_at_datetime") or _obj_value(tweet, "created_at"),
        lang=_optional_text(_obj_value(tweet, "lang")),
        url=_optional_text(_obj_value(tweet, "url")),
        reply_count=_obj_value(tweet, "reply_count"),
        retweet_count=_obj_value(tweet, "retweet_count"),
        favorite_count=_obj_value(tweet, "favorite_count"),
        view_count=_obj_value(tweet, "view_count"),
        payload=_object_payload(tweet),
    )


def _object_payload(obj: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name in (
        "id",
        "text",
        "full_text",
        "created_at",
        "created_at_datetime",
        "lang",
        "reply_count",
        "retweet_count",
        "favorite_count",
        "view_count",
        "url",
    ):
        value = _obj_value(obj, name)
        if value is None:
            continue
        payload[name] = value.isoformat() if isinstance(value, datetime) else value
    return payload


def _obj_value(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _build_english_summary(
    prefix: str | None,
    account: AccountConfig,
    text: str,
) -> str | None:
    if not prefix:
        return None
    return f"{prefix} @{account.account}: {text[:96]}"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any, label: str) -> str:
    text = _optional_text(value)
    if not text:
        raise XClientError(f"X post normalization requires {label.lower()}.")
    return text


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
