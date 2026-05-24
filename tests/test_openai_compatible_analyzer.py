from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from trade_trend_kit.domain.errors import AnalysisError
from trade_trend_kit.domain.models import AccountConfig, AccountMeta, NormalizedTweet
from trade_trend_kit.infra.llm.openai_compatible import (
    OpenAICompatibleAnalyzer,
    OpenAICompatibleSettings,
)
from trade_trend_kit.infra.llm.error_archive import JsonLLMErrorArchive
from trade_trend_kit.utils.json_io import read_json_file

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def fixed_clock(_: str) -> datetime:
    return datetime(2026, 5, 23, 11, 0, tzinfo=PROJECT_TZ)


def make_account() -> AccountConfig:
    return AccountConfig(
        account="macro_blogger",
        display_name="Macro Blogger",
        market="US_STOCK",
        category="macro",
        tags=["fed", "ai"],
        watch_symbols=["NVDA"],
    )


def make_tweet(account: AccountConfig, tweet_id: str = "tweet-1") -> NormalizedTweet:
    return NormalizedTweet(
        tweet_id=tweet_id,
        account=account.account,
        display_name=account.display_name,
        user_id="user-1",
        created_at=datetime(2026, 5, 23, 10, 30, tzinfo=PROJECT_TZ),
        text="NVDA capex and AI demand remain constructive, but rates are a risk.",
        english_summary="NVDA demand remains constructive with rate risk.",
        lang="en",
        url=f"https://x.com/{account.account}/status/{tweet_id}",
        account_meta=AccountMeta.from_account_config(account),
        fetched_at=datetime(2026, 5, 23, 10, 35, tzinfo=PROJECT_TZ),
    )


def make_settings() -> OpenAICompatibleSettings:
    return OpenAICompatibleSettings(
        base_url="https://provider.example/v1",
        api_key="test-key",
        model="test-model",
        timezone="Asia/Shanghai",
    )


def make_llm_payload(tweet_id: str = "tweet-1") -> dict[str, Any]:
    return {
        "english_source_summaries": [
            {"tweet_id": tweet_id, "summary": "NVDA demand remains constructive."}
        ],
        "chinese_report": {
            "summary": "该账号认为 AI 需求仍有支撑，但利率风险需要跟踪。",
            "market_direction": "偏多但需谨慎",
            "key_themes": ["AI 资本开支", "利率风险"],
            "mentioned_symbols": ["NVDA"],
            "stock_watchlist": [
                {
                    "symbol": "NVDA",
                    "direction": "关注",
                    "reason": "推文提到 AI 需求仍具建设性。",
                    "confidence": "medium",
                    "risk": "利率上行可能压制估值。",
                }
            ],
            "risk_notes": ["不要把单条推文视为交易信号。"],
        },
    }


def completion_with_content(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}]}


def test_openai_compatible_analyzer_builds_domain_report() -> None:
    account = make_account()
    tweet = make_tweet(account)
    calls: list[dict[str, Any]] = []

    def transport(
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        calls.append(
            {
                "url": url,
                "headers": headers,
                "payload": payload,
                "timeout_seconds": timeout_seconds,
            }
        )
        content = json.dumps(make_llm_payload(tweet.tweet_id), ensure_ascii=False)
        return completion_with_content(content)

    analyzer = OpenAICompatibleAnalyzer(
        settings=make_settings(),
        transport=transport,
        clock=fixed_clock,
    )

    report = asyncio.run(analyzer.analyze_account_tweets(account, [tweet]))

    assert report.report_id == "20260523110000_US_STOCK_macro_macro_blogger_tweet-1"
    assert report.date == "2026-05-23"
    assert report.new_tweet_count == 1
    assert report.source_tweet_ids == ["tweet-1"]
    assert report.english_source_summaries[0].summary == "NVDA demand remains constructive."
    assert report.chinese_report.mentioned_symbols == ["NVDA"]
    assert report.chinese_report.stock_watchlist[0].confidence == "medium"
    assert calls[0]["url"] == "https://provider.example/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert calls[0]["payload"]["response_format"] == {"type": "json_object"}


def test_openai_compatible_analyzer_repairs_invalid_json_once() -> None:
    account = make_account()
    tweet = make_tweet(account)
    responses = [
        completion_with_content("not-json"),
        completion_with_content(json.dumps(make_llm_payload(tweet.tweet_id), ensure_ascii=False)),
    ]
    payloads: list[dict[str, Any]] = []

    def transport(
        _: str,
        __: dict[str, str],
        payload: dict[str, Any],
        ___: float,
    ) -> dict[str, Any]:
        payloads.append(payload)
        return responses.pop(0)

    analyzer = OpenAICompatibleAnalyzer(
        settings=make_settings(),
        transport=transport,
        clock=fixed_clock,
    )

    report = asyncio.run(analyzer.analyze_account_tweets(account, [tweet]))

    assert report.chinese_report.summary.startswith("该账号认为")
    assert len(payloads) == 2
    assert "Repair it and return JSON only" in payloads[1]["messages"][1]["content"]


def test_openai_compatible_analyzer_falls_back_missing_english_summary() -> None:
    account = make_account()
    tweet = make_tweet(account)
    payload = make_llm_payload(tweet.tweet_id)
    payload["english_source_summaries"] = []

    def transport(
        _: str,
        __: dict[str, str],
        ___: dict[str, Any],
        ____: float,
    ) -> dict[str, Any]:
        return completion_with_content(json.dumps(payload, ensure_ascii=False))

    analyzer = OpenAICompatibleAnalyzer(
        settings=make_settings(),
        transport=transport,
        clock=fixed_clock,
    )

    report = asyncio.run(analyzer.analyze_account_tweets(account, [tweet]))

    assert report.english_source_summaries[0].summary == tweet.english_summary


def test_openai_compatible_analyzer_requires_api_key() -> None:
    settings = OpenAICompatibleSettings(api_key=None)

    with pytest.raises(AnalysisError, match="LLM_API_KEY"):
        OpenAICompatibleAnalyzer(settings=settings)


def test_openai_compatible_analyzer_archives_failed_json_repair(tmp_path: Path) -> None:
    account = make_account()
    tweet = make_tweet(account)
    responses = [
        completion_with_content("not-json"),
        completion_with_content("still not json"),
    ]

    def transport(
        _: str,
        __: dict[str, str],
        ___: dict[str, Any],
        ____: float,
    ) -> dict[str, Any]:
        return responses.pop(0)

    analyzer = OpenAICompatibleAnalyzer(
        settings=make_settings(),
        transport=transport,
        clock=fixed_clock,
        error_archive=JsonLLMErrorArchive(tmp_path / "reports"),
    )

    with pytest.raises(AnalysisError, match="Archived at"):
        asyncio.run(analyzer.analyze_account_tweets(account, [tweet]))

    archive_paths = list((tmp_path / "reports" / "2026-05-23" / "errors").glob("*.json"))
    assert len(archive_paths) == 1
    archive = read_json_file(archive_paths[0])
    assert archive["stage"] == "json_repair_failed"
    assert archive["account"]["account"] == "macro_blogger"
    assert archive["source_tweet_ids"] == ["tweet-1"]
    assert archive["raw_response"] == "not-json"
    assert archive["repair_response"] == "still not json"
    assert "test-key" not in json.dumps(archive)
