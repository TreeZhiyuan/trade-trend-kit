"""Local JSON tweet repository adapter.

The repository keeps one daily file per account for raw tweets and normalized
tweets. Saving the same account/day again merges by `tweet_id`, so repeated
scheduled fetches preserve the day's unique tweet set instead of overwriting it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_trend_kit.domain.errors import StorageError
from trade_trend_kit.domain.models import NormalizedTweet, RawTweetBatch
from trade_trend_kit.domain.ports import TweetRepository
from trade_trend_kit.utils.filenames import build_account_file_stem, build_report_file_stem
from trade_trend_kit.utils.json_io import read_json_file, write_json_file
from trade_trend_kit.utils.time import DEFAULT_TIMEZONE, date_key

DEFAULT_RAW_TWEETS_DIR = Path("data/raw_tweets")
DEFAULT_NORMALIZED_TWEETS_DIR = Path("data/normalized_tweets")


class JsonTweetRepository(TweetRepository):
    """Persist raw and normalized tweets as daily JSON files."""

    def __init__(
        self,
        raw_dir: Path | str = DEFAULT_RAW_TWEETS_DIR,
        normalized_dir: Path | str = DEFAULT_NORMALIZED_TWEETS_DIR,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> None:
        self.raw_dir = Path(raw_dir)
        self.normalized_dir = Path(normalized_dir)
        self.timezone = timezone

    async def save_raw(self, batch: RawTweetBatch) -> None:
        """Save a raw batch, merging unique tweets into the account's daily file."""

        path = self._raw_path(batch)
        payload = batch.model_dump(mode="json")
        payload["date"] = date_key(batch.fetched_at, self.timezone)
        payload["tweets"] = self._merge_tweets(path, payload["tweets"])
        payload["tweet_count"] = len(payload["tweets"])
        write_json_file(path, payload)

    async def save_normalized(self, tweets: list[NormalizedTweet]) -> None:
        """Save normalized tweets, merging unique tweets into one daily account file."""

        if not tweets:
            return

        self._ensure_single_normalized_bucket(tweets)
        first = tweets[0]
        path = self._normalized_path(first)
        rows = [tweet.model_dump(mode="json") for tweet in tweets]
        merged_rows = self._merge_tweets(path, rows)
        payload = {
            "account": first.account,
            "display_name": first.display_name,
            "market": first.account_meta.market,
            "category": first.account_meta.category,
            "date": date_key(first.fetched_at, self.timezone),
            "fetched_at": first.model_dump(mode="json")["fetched_at"],
            "tweet_count": len(merged_rows),
            "tweets": merged_rows,
        }
        write_json_file(path, payload)

    def _raw_path(self, batch: RawTweetBatch) -> Path:
        file_name = f"{build_account_file_stem(batch.account.file_key)}.json"
        return self.raw_dir / date_key(batch.fetched_at, self.timezone) / file_name

    def _normalized_path(self, tweet: NormalizedTweet) -> Path:
        file_name = (
            f"{build_report_file_stem(tweet.account_meta.market, tweet.account_meta.category, tweet.account)}.json"
        )
        return self.normalized_dir / date_key(tweet.fetched_at, self.timezone) / file_name

    def _merge_tweets(
        self,
        path: Path,
        new_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        existing_payload = read_json_file(path, default={})
        if not isinstance(existing_payload, dict):
            raise StorageError(f"Tweet storage file must contain an object: {path}")

        existing_rows = existing_payload.get("tweets", [])
        if not isinstance(existing_rows, list):
            raise StorageError(f"Tweet storage file must contain a tweets list: {path}")

        merged: dict[str, dict[str, Any]] = {}
        for row in [*existing_rows, *new_rows]:
            if not isinstance(row, dict) or "tweet_id" not in row:
                raise StorageError(f"Tweet row is missing tweet_id in storage file: {path}")
            merged[str(row["tweet_id"])] = row
        return list(merged.values())

    def _ensure_single_normalized_bucket(self, tweets: list[NormalizedTweet]) -> None:
        first = tweets[0]
        first_stem = build_report_file_stem(
            first.account_meta.market,
            first.account_meta.category,
            first.account,
        )
        first_date = date_key(first.fetched_at, self.timezone)

        for tweet in tweets[1:]:
            tweet_stem = build_report_file_stem(
                tweet.account_meta.market,
                tweet.account_meta.category,
                tweet.account,
            )
            tweet_date = date_key(tweet.fetched_at, self.timezone)
            if tweet_stem != first_stem or tweet_date != first_date:
                raise StorageError("Normalized tweets must belong to one account and date bucket.")
