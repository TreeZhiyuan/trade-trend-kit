"""Twikit-backed X post client adapter.

Twikit-specific imports and object conversions stay in this adapter so domain
and application code remain independent from SDK object shapes.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from trade_trend_kit.domain.errors import AuthenticationError, RateLimitError, XClientError
from trade_trend_kit.domain.models import (
    AccountConfig,
    FetchResult,
    RawTweetBatch,
    XUser,
)
from trade_trend_kit.domain.ports import XPostClient
from trade_trend_kit.infra.x.normalizer import (
    build_raw_tweets,
    normalize_x_posts,
    twikit_tweet_to_raw_post,
)
from trade_trend_kit.utils.env import load_env_file
from trade_trend_kit.utils.time import DEFAULT_TIMEZONE, now_in_timezone

DEFAULT_COOKIES_PATH = Path("data/runtime/cookies.json")
TWEET_PRODUCT = "Tweets"


@dataclass(frozen=True)
class TwikitSettings:
    """Runtime settings for the Twikit adapter."""

    username: str | None = None
    email: str | None = None
    password: str | None = None
    cookies_path: Path = DEFAULT_COOKIES_PATH
    reuse_cookies: bool = True
    language: str = "en-US"
    proxy: str | None = None
    timezone: str = DEFAULT_TIMEZONE

    @classmethod
    def from_env(
        cls,
        env_file: Path | str = Path(".env"),
        default_cookies_path: Path = DEFAULT_COOKIES_PATH,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> "TwikitSettings":
        """Build settings from `.env` and process environment variables."""

        load_env_file(env_file)
        return cls(
            username=_optional_env("X_USERNAME"),
            email=_optional_env("X_EMAIL"),
            password=_optional_env("X_PASSWORD"),
            cookies_path=Path(os.environ.get("TWIKIT_COOKIES_PATH") or default_cookies_path),
            reuse_cookies=_bool_env("TWIKIT_REUSE_COOKIES", default=True),
            language=os.environ.get("TWIKIT_LANGUAGE") or "en-US",
            proxy=_optional_env("TWIKIT_PROXY"),
            timezone=timezone,
        )


class TwikitXPostClient(XPostClient):
    """Fetch and normalize latest posts through Twikit."""

    def __init__(
        self,
        settings: TwikitSettings,
        client: Any | None = None,
    ) -> None:
        self.settings = settings
        self._client = client
        self._authenticated = False

    async def fetch_latest_posts(self, account: AccountConfig, limit: int) -> FetchResult:
        """Fetch latest tweets for one account and convert them to domain models."""

        client = await self._ensure_client()
        try:
            user_obj = await _maybe_await(client.get_user_by_screen_name(account.account))
            twikit_tweets = await _fetch_user_tweets(client, user_obj, limit)
        except Exception as exc:  # noqa: BLE001 - normalize SDK-specific exceptions.
            raise _map_twikit_error(exc, f"Failed to fetch @{account.account}") from exc

        fetched_at = now_in_timezone(self.settings.timezone)
        user = _to_x_user(user_obj, account)
        tweet_items = [twikit_tweet_to_raw_post(tweet) for tweet in list(twikit_tweets)[:limit]]
        raw_tweets = build_raw_tweets(tweet_items, account, user, fetched_at)
        normalized_tweets = normalize_x_posts(
            tweet_items,
            account=account,
            user=user,
            fetched_at=fetched_at,
            timezone=self.settings.timezone,
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

    async def _ensure_client(self) -> Any:
        """Create and authenticate the Twikit client lazily."""

        if self._client is None:
            self._client = _create_twikit_client(self.settings)
        if self._authenticated:
            return self._client

        await self._authenticate()
        self._authenticated = True
        return self._client

    async def _authenticate(self) -> None:
        client = self._client
        if client is None:
            raise AuthenticationError("Twikit client was not initialized.")

        self.settings.cookies_path.parent.mkdir(parents=True, exist_ok=True)
        cookies_failed = False
        if self.settings.reuse_cookies and self.settings.cookies_path.exists():
            try:
                client.load_cookies(str(self.settings.cookies_path))
                return
            except Exception as exc:  # noqa: BLE001 - fall back to login when credentials exist.
                if not self._has_login_credentials:
                    raise AuthenticationError(
                        f"Unable to load Twikit cookies: {self.settings.cookies_path}: {exc}"
                    ) from exc
                cookies_failed = True

        if not self._has_login_credentials:
            raise AuthenticationError(
                "Twikit login requires X_USERNAME and X_PASSWORD, "
                "or a valid TWIKIT_COOKIES_PATH file."
            )

        try:
            cookies_file = None
            if self.settings.reuse_cookies and not cookies_failed:
                cookies_file = str(self.settings.cookies_path)
            client.login(
                auth_info_1=self.settings.username,
                auth_info_2=self.settings.email,
                password=self.settings.password,
                cookies_file=cookies_file,
            )
            if hasattr(client, "save_cookies"):
                client.save_cookies(str(self.settings.cookies_path))
        except Exception as exc:  # noqa: BLE001 - normalize SDK-specific exceptions.
            raise _map_twikit_error(exc, "Twikit login failed") from exc

    @property
    def _has_login_credentials(self) -> bool:
        return all([self.settings.username, self.settings.password])


def _create_twikit_client(settings: TwikitSettings) -> Any:
    """Import Twikit only when the real adapter is used."""

    try:
        from twikit import Client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise XClientError(
            "Twikit is not installed. Run `python -m pip install -r requirements.txt`."
        ) from exc

    kwargs: dict[str, Any] = {"language": settings.language}
    if settings.proxy:
        kwargs["proxy"] = settings.proxy
    return Client(**kwargs)


def _to_x_user(user_obj: Any, account: AccountConfig) -> XUser:
    user_id = _required_str(_obj_value(user_obj, "id") or _obj_value(user_obj, "user_id"), "User id")
    return XUser(
        user_id=user_id,
        account=str(_obj_value(user_obj, "screen_name") or account.account),
        display_name=_optional_str(_obj_value(user_obj, "name") or account.display_name),
    )


async def _fetch_user_tweets(client: Any, user_obj: Any, limit: int) -> Any:
    user_id = _required_str(_obj_value(user_obj, "id") or _obj_value(user_obj, "user_id"), "User id")
    if hasattr(client, "get_user_tweets"):
        return await _maybe_await(client.get_user_tweets(user_id, TWEET_PRODUCT, count=limit))
    if hasattr(user_obj, "get_tweets"):
        return await _maybe_await(user_obj.get_tweets(TWEET_PRODUCT, count=limit))
    raise XClientError("Twikit client cannot fetch user tweets.")


def _obj_value(obj: Any, name: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _map_twikit_error(exc: Exception, message: str) -> XClientError:
    name = exc.__class__.__name__.lower()
    text = str(exc)
    combined = f"{name} {text}".lower()
    if any(
        token in combined
        for token in (
            "unauthorized",
            "forbidden",
            "accountlocked",
            "accountsuspended",
            "login",
            "auth",
            "cookie",
        )
    ):
        return AuthenticationError(f"{message}: {text}")
    if any(
        token in combined
        for token in ("ratelimit", "rate limit", "too many requests", "toomanyrequests", "429")
    ):
        return RateLimitError(f"{message}: {text}")
    return XClientError(f"{message}: {text}")


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _required_str(value: Any, label: str) -> str:
    if value is None:
        raise XClientError(f"Twikit returned no {label.lower()}.")
    text = str(value).strip()
    if not text:
        raise XClientError(f"Twikit returned empty {label.lower()}.")
    return text
