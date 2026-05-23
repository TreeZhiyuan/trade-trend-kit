from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from trade_trend_kit.domain.errors import AuthenticationError, RateLimitError, XClientError
from trade_trend_kit.domain.models import AccountConfig
from trade_trend_kit.infra.x.twikit_client import TwikitSettings, TwikitXPostClient
from trade_trend_kit.cli import build_parser

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


class FakeTwikitClient:
    def __init__(self) -> None:
        self.loaded_cookies = None
        self.login_calls = []
        self.saved_cookies = None
        self.user_calls = []
        self.tweet_calls = []
        self.user = SimpleNamespace(id="123", screen_name="macro_blogger", name="Macro Blogger")
        self.tweets = [
            SimpleNamespace(
                id="t1",
                full_text="Fed\n liquidity   matter.",
                created_at_datetime=datetime(2026, 5, 23, 9, 0, tzinfo=PROJECT_TZ),
                lang="en",
                reply_count=1,
                retweet_count=2,
                favorite_count=3,
                view_count=4,
            )
        ]

    def load_cookies(self, path: str):
        self.loaded_cookies = path
        return None

    def login(
        self,
        auth_info_1: str | None = None,
        auth_info_2: str | None = None,
        password: str | None = None,
        cookies_file: str | None = None,
    ):
        self.login_calls.append((auth_info_1, auth_info_2, password, cookies_file))
        return None

    def save_cookies(self, path: str):
        self.saved_cookies = path
        return None

    def get_user_by_screen_name(self, screen_name: str):
        self.user_calls.append(screen_name)
        return self.user

    def get_user_tweets(self, user_id: str, product: str, count: int = 10):
        self.tweet_calls.append((user_id, product, count))
        return self.tweets


def make_account() -> AccountConfig:
    return AccountConfig(account="macro_blogger", market="US_STOCK", category="macro")


def test_cli_parser_accepts_twikit_mode() -> None:
    parser = build_parser()

    args = parser.parse_args(["fetch-once", "--twikit"])

    assert args.command == "fetch-once"
    assert args.twikit is True


def test_twikit_client_loads_cookies_and_fetches_tweets(tmp_path: Path) -> None:
    cookies_path = tmp_path / "cookies.json"
    cookies_path.write_text("{}", encoding="utf-8")
    client = FakeTwikitClient()
    settings = TwikitSettings(
        username="user",
        password="pass",
        cookies_path=cookies_path,
        reuse_cookies=True,
        language="en-US",
        timezone="Asia/Shanghai",
    )
    adapter = TwikitXPostClient(settings=settings, client=client)

    result = asyncio.run(adapter.fetch_latest_posts(make_account(), limit=1))

    assert client.loaded_cookies == str(cookies_path)
    assert client.login_calls == []
    assert client.user_calls == ["macro_blogger"]
    assert client.tweet_calls == [("123", "Tweets", 1)]
    assert result.user.user_id == "123"
    assert result.normalized_tweets[0].tweet_id == "t1"
    assert result.normalized_tweets[0].text == "Fed liquidity matter."


def test_twikit_client_logs_in_when_cookies_missing(tmp_path: Path) -> None:
    client = FakeTwikitClient()
    cookies_path = tmp_path / "cookies.json"
    settings = TwikitSettings(
        username="user",
        password="pass",
        cookies_path=cookies_path,
        reuse_cookies=True,
        language="en-US",
        timezone="Asia/Shanghai",
    )
    adapter = TwikitXPostClient(settings=settings, client=client)

    asyncio.run(adapter.fetch_latest_posts(make_account(), limit=1))

    assert client.login_calls == [("user", None, "pass", str(cookies_path))]
    assert client.saved_cookies == str(cookies_path)


def test_twikit_client_can_use_loaded_cookies_without_relogin(tmp_path: Path) -> None:
    cookies_path = tmp_path / "cookies.json"
    cookies_path.write_text("{}", encoding="utf-8")
    client = FakeTwikitClient()
    settings = TwikitSettings(
        cookies_path=cookies_path,
        reuse_cookies=True,
        language="en-US",
        timezone="Asia/Shanghai",
    )
    adapter = TwikitXPostClient(settings=settings, client=client)

    asyncio.run(adapter.fetch_latest_posts(make_account(), limit=1))

    assert client.loaded_cookies == str(cookies_path)
    assert client.login_calls == []


def test_twikit_client_maps_rate_limit_errors() -> None:
    class ErrorClient(FakeTwikitClient):
        def get_user_by_screen_name(self, screen_name: str):  # type: ignore[override]
            raise RuntimeError("429 TooManyRequests")

    adapter = TwikitXPostClient(
        settings=TwikitSettings(username="user", password="pass"),
        client=ErrorClient(),
    )

    with pytest.raises(RateLimitError):
        asyncio.run(adapter.fetch_latest_posts(make_account(), limit=1))


def test_twikit_client_requires_login_or_cookies(tmp_path: Path) -> None:
    adapter = TwikitXPostClient(
        settings=TwikitSettings(cookies_path=tmp_path / "missing.json"),
        client=FakeTwikitClient(),
    )

    with pytest.raises(AuthenticationError):
        asyncio.run(adapter.fetch_latest_posts(make_account(), limit=1))


def test_twikit_client_rejects_missing_tweet_id() -> None:
    class MissingIdClient(FakeTwikitClient):
        def get_user_tweets(self, user_id: str, product: str, count: int = 10):  # type: ignore[override]
            return [SimpleNamespace(full_text="bad tweet")]

    adapter = TwikitXPostClient(
        settings=TwikitSettings(username="user", password="pass"),
        client=MissingIdClient(),
    )

    with pytest.raises(XClientError):
        asyncio.run(adapter.fetch_latest_posts(make_account(), limit=1))
