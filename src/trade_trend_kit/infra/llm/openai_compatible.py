"""OpenAI-compatible LLM analyzer adapter.

Keeping the provider isolated here makes it easy to swap models or vendors
without changing analysis orchestration code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from trade_trend_kit.domain.errors import AnalysisError
from trade_trend_kit.domain.models import (
    AccountConfig,
    AccountIncrementalReport,
    ChineseAccountReport,
    EnglishSourceSummary,
    NormalizedTweet,
)
from trade_trend_kit.domain.ports import TweetAnalyzer
from trade_trend_kit.infra.llm.error_archive import LLMErrorArchive, LLMErrorArchiveRecord
from trade_trend_kit.infra.llm.prompts import (
    build_account_analysis_messages,
    build_json_repair_messages,
)
from trade_trend_kit.utils.env import load_env_file
from trade_trend_kit.utils.time import DEFAULT_TIMEZONE, date_key, now_in_timezone

DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_LLM_TIMEOUT_SECONDS = 60.0
DEFAULT_LLM_TEMPERATURE = 0.2

JsonObject = dict[str, Any]
LLMTransport = Callable[[str, dict[str, str], JsonObject, float], JsonObject]
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAICompatibleSettings:
    """Runtime settings for an OpenAI-compatible chat/completions provider."""

    base_url: str = DEFAULT_LLM_BASE_URL
    api_key: str | None = None
    model: str = DEFAULT_LLM_MODEL
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS
    temperature: float = DEFAULT_LLM_TEMPERATURE
    max_tokens: int | None = None
    timezone: str = DEFAULT_TIMEZONE
    language: str = "zh-CN"
    preserve_english_summary: bool = True

    @classmethod
    def from_env(
        cls,
        env_file: str | Path = Path(".env"),
        timezone: str = DEFAULT_TIMEZONE,
        language: str = "zh-CN",
        preserve_english_summary: bool = True,
    ) -> "OpenAICompatibleSettings":
        """Load provider settings from environment variables and `.env`."""

        load_env_file(env_file)
        return cls(
            base_url=os.environ.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL,
            api_key=_optional_env("LLM_API_KEY"),
            model=os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL,
            timeout_seconds=_float_env(
                "LLM_TIMEOUT_SECONDS",
                default=DEFAULT_LLM_TIMEOUT_SECONDS,
            ),
            temperature=_float_env("LLM_TEMPERATURE", default=DEFAULT_LLM_TEMPERATURE),
            max_tokens=_optional_int_env("LLM_MAX_TOKENS"),
            timezone=timezone,
            language=language,
            preserve_english_summary=preserve_english_summary,
        )

    def validate(self) -> None:
        """Fail fast before a run starts if provider settings are incomplete."""

        if not self.api_key:
            raise AnalysisError("LLM_API_KEY is required when --llm analysis is enabled.")
        if not self.base_url.strip():
            raise AnalysisError("LLM_BASE_URL cannot be empty.")
        if not self.model.strip():
            raise AnalysisError("LLM_MODEL cannot be empty.")
        if self.timeout_seconds <= 0:
            raise AnalysisError("LLM_TIMEOUT_SECONDS must be greater than 0.")
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise AnalysisError("LLM_MAX_TOKENS must be greater than 0 when provided.")


class OpenAICompatibleAnalyzer(TweetAnalyzer):
    """Analyze new tweets through an OpenAI-compatible chat/completions API."""

    def __init__(
        self,
        settings: OpenAICompatibleSettings,
        transport: LLMTransport | None = None,
        clock: Callable[[str], datetime] | None = None,
        error_archive: LLMErrorArchive | None = None,
    ) -> None:
        settings.validate()
        self.settings = settings
        self.transport = transport or _urllib_json_transport
        self.clock = clock or now_in_timezone
        self.error_archive = error_archive

    async def analyze_account_tweets(
        self,
        account: AccountConfig,
        tweets: list[NormalizedTweet],
    ) -> AccountIncrementalReport:
        """Analyze only the incremental tweets selected by application services."""

        started_at = perf_counter()
        LOGGER.info(
            "LLM analysis started: account=%s tweet_count=%s model=%s",
            account.account,
            len(tweets),
            self.settings.model,
        )
        messages = build_account_analysis_messages(
            account=account,
            tweets=tweets,
            language=self.settings.language,
            preserve_english_summary=self.settings.preserve_english_summary,
        )

        try:
            raw_response = await asyncio.to_thread(self._chat_completion, messages)
            raw_content = _extract_message_content(raw_response)
        except AnalysisError:
            LOGGER.exception(
                "LLM analysis failed before parsing response: account=%s tweet_count=%s",
                account.account,
                len(tweets),
            )
            raise

        try:
            parsed_response = _parse_json_object(raw_content)
        except AnalysisError:
            LOGGER.warning(
                "LLM returned invalid JSON; attempting one repair: account=%s tweet_count=%s",
                account.account,
                len(tweets),
            )
            repaired_content = ""
            try:
                repaired_response = await asyncio.to_thread(
                    self._chat_completion,
                    build_json_repair_messages(raw_content),
                )
                repaired_content = _extract_message_content(repaired_response)
                parsed_response = _parse_json_object(repaired_content)
            except AnalysisError as repair_error:
                archive_path = self._archive_invalid_json_response(
                    account=account,
                    tweets=tweets,
                    raw_content=raw_content,
                    repair_content=repaired_content,
                    error=repair_error,
                )
                archive_hint = f" Archived at: {archive_path}" if archive_path else ""
                raise AnalysisError(
                    f"LLM returned invalid JSON after repair for @{account.account}."
                    f"{archive_hint}"
                ) from repair_error

        created_at = self.clock(self.settings.timezone)
        report = _build_account_report(
            account=account,
            tweets=tweets,
            response=parsed_response,
            created_at=created_at,
            timezone=self.settings.timezone,
        )
        duration_ms = int((perf_counter() - started_at) * 1000)
        LOGGER.info(
            "LLM analysis finished: account=%s tweet_count=%s report_id=%s duration_ms=%s",
            account.account,
            len(tweets),
            report.report_id,
            duration_ms,
        )
        return report

    def _chat_completion(self, messages: list[dict[str, str]]) -> JsonObject:
        payload: JsonObject = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
            "response_format": {"type": "json_object"},
        }
        if self.settings.max_tokens is not None:
            payload["max_tokens"] = self.settings.max_tokens

        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.settings.base_url.rstrip('/')}/chat/completions"
        started_at = perf_counter()
        try:
            response = self.transport(url, headers, payload, self.settings.timeout_seconds)
            duration_ms = int((perf_counter() - started_at) * 1000)
            LOGGER.info(
                "LLM chat completion request finished: model=%s duration_ms=%s",
                self.settings.model,
                duration_ms,
            )
            return response
        except AnalysisError:
            duration_ms = int((perf_counter() - started_at) * 1000)
            LOGGER.warning(
                "LLM chat completion request failed: model=%s duration_ms=%s",
                self.settings.model,
                duration_ms,
            )
            raise
        except Exception as exc:  # noqa: BLE001 - normalize provider/transport failures.
            duration_ms = int((perf_counter() - started_at) * 1000)
            LOGGER.warning(
                "LLM chat completion request failed: model=%s duration_ms=%s",
                self.settings.model,
                duration_ms,
            )
            raise AnalysisError(f"LLM request failed: {exc}") from exc

    def _archive_invalid_json_response(
        self,
        account: AccountConfig,
        tweets: list[NormalizedTweet],
        raw_content: str,
        repair_content: str,
        error: AnalysisError,
    ) -> Path | None:
        if self.error_archive is None:
            LOGGER.warning(
                "LLM invalid JSON archive skipped because no archive backend is configured: "
                "account=%s",
                account.account,
            )
            return None

        created_at = self.clock(self.settings.timezone)
        path = self.error_archive.save(
            LLMErrorArchiveRecord(
                account=account,
                source_tweet_ids=[tweet.tweet_id for tweet in tweets],
                stage="json_repair_failed",
                error_message=str(error),
                raw_response=raw_content,
                repair_response=repair_content,
                created_at=created_at,
                timezone=self.settings.timezone,
                model=self.settings.model,
            )
        )
        LOGGER.error(
            "Archived invalid LLM response: account=%s tweet_count=%s path=%s",
            account.account,
            len(tweets),
            path,
        )
        return path


def _urllib_json_transport(
    url: str,
    headers: dict[str, str],
    payload: JsonObject,
    timeout_seconds: float,
) -> JsonObject:
    """Send one JSON HTTP request using stdlib so no SDK is required."""

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise AnalysisError(
            f"LLM request failed with HTTP {exc.code}: {_clip(error_body)}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AnalysisError(f"LLM request failed: {exc}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"LLM response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AnalysisError("LLM response root must be a JSON object.")
    return parsed


def _build_account_report(
    account: AccountConfig,
    tweets: list[NormalizedTweet],
    response: JsonObject,
    created_at: datetime,
    timezone: str,
) -> AccountIncrementalReport:
    """Convert model JSON into the project-owned report model."""

    source_tweet_ids = [tweet.tweet_id for tweet in tweets]
    chinese_payload = response.get("chinese_report")
    chinese_report = _parse_chinese_report(chinese_payload)
    english_summaries = _parse_english_summaries(
        response.get("english_source_summaries"),
        tweets,
    )

    return AccountIncrementalReport(
        report_id=_build_report_id(account, source_tweet_ids, created_at),
        date=date_key(created_at, timezone),
        account=account.account,
        market=account.market,
        category=account.category,
        new_tweet_count=len(tweets),
        source_tweet_ids=source_tweet_ids,
        english_source_summaries=english_summaries,
        chinese_report=chinese_report,
        created_at=created_at,
    )


def _parse_chinese_report(value: Any) -> ChineseAccountReport:
    if not isinstance(value, dict):
        raise AnalysisError("LLM JSON must contain a chinese_report object.")

    allowed_keys = {
        "summary",
        "market_direction",
        "key_themes",
        "mentioned_symbols",
        "stock_watchlist",
        "risk_notes",
    }
    payload = {key: value[key] for key in allowed_keys if key in value}
    payload["stock_watchlist"] = _sanitize_stock_watchlist(payload.get("stock_watchlist"))

    try:
        return ChineseAccountReport.model_validate(payload)
    except ValidationError as exc:
        raise AnalysisError(f"LLM chinese_report shape is invalid: {exc}") from exc


def _sanitize_stock_watchlist(value: Any) -> list[JsonObject]:
    if not isinstance(value, list):
        return []

    allowed_keys = {"symbol", "direction", "reason", "confidence", "risk"}
    items: list[JsonObject] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        item = {key: raw_item[key] for key in allowed_keys if key in raw_item}
        if item.get("confidence") not in {"low", "medium", "high"}:
            item["confidence"] = "medium"
        items.append(item)
    return items


def _parse_english_summaries(value: Any, tweets: list[NormalizedTweet]) -> list[EnglishSourceSummary]:
    source_tweet_ids = [tweet.tweet_id for tweet in tweets]
    source_tweet_id_set = set(source_tweet_ids)
    summaries_by_id: dict[str, EnglishSourceSummary] = {}

    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            tweet_id = str(item.get("tweet_id") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if tweet_id in source_tweet_id_set and summary:
                summaries_by_id[tweet_id] = EnglishSourceSummary(
                    tweet_id=tweet_id,
                    summary=summary,
                )

    # Fill missing English summaries from normalized tweet data so downstream
    # report consumers always have one source summary per analyzed tweet.
    for tweet in tweets:
        if tweet.tweet_id not in summaries_by_id:
            summaries_by_id[tweet.tweet_id] = EnglishSourceSummary(
                tweet_id=tweet.tweet_id,
                summary=_fallback_summary(tweet),
            )

    return [summaries_by_id[tweet_id] for tweet_id in source_tweet_ids]


def _extract_message_content(response: JsonObject) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AnalysisError("LLM response is missing choices.")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise AnalysisError("LLM response choice must be an object.")

    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = first_choice.get("text")

    text = _content_to_text(content)
    if not text.strip():
        raise AnalysisError("LLM response content is empty.")
    return text


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return ""


def _parse_json_object(raw_text: str) -> JsonObject:
    candidate = _extract_json_candidate(raw_text)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"LLM returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AnalysisError("LLM analysis JSON root must be an object.")
    return parsed


def _extract_json_candidate(raw_text: str) -> str:
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.startswith("{") and text.endswith("}"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _build_report_id(
    account: AccountConfig,
    source_tweet_ids: list[str],
    created_at: datetime,
) -> str:
    tweet_part = "-".join(source_tweet_ids[:3]) or "empty"
    timestamp = created_at.strftime("%Y%m%d%H%M%S")
    return f"{timestamp}_{account.market}_{account.category}_{account.account}_{tweet_part}"


def _fallback_summary(tweet: NormalizedTweet) -> str:
    if tweet.english_summary:
        return tweet.english_summary
    return " ".join(tweet.text.split())[:160]


def _optional_env(key: str) -> str | None:
    value = os.environ.get(key)
    if value is None or not value.strip():
        return None
    return value.strip()


def _float_env(key: str, default: float) -> float:
    value = os.environ.get(key)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise AnalysisError(f"{key} must be a number.") from exc


def _optional_int_env(key: str) -> int | None:
    value = os.environ.get(key)
    if value is None or not value.strip():
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise AnalysisError(f"{key} must be an integer.") from exc


def _clip(text: str, limit: int = 500) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit]}..."
