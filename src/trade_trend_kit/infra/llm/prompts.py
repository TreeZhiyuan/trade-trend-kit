"""Prompt templates for tweet analysis.

Prompt text is separated from provider code so report shape changes can be
reviewed without touching HTTP/client logic.
"""

from __future__ import annotations

import json

from trade_trend_kit.domain.models import AccountConfig, NormalizedTweet

SYSTEM_PROMPT = """You are an investment research assistant.
Analyze public X posts for research only. Return strict JSON that matches the
requested schema. Do not invent symbols, prices, events, or sources that are
not supported by the provided tweets.
"""


def build_account_analysis_messages(
    account: AccountConfig,
    tweets: list[NormalizedTweet],
    language: str = "zh-CN",
    preserve_english_summary: bool = True,
) -> list[dict[str, str]]:
    """Build OpenAI-compatible chat messages for account-level analysis."""

    payload = {
        "account": {
            "account": account.account,
            "display_name": account.display_name,
            "market": account.market,
            "category": account.category,
            "region": account.region,
            "tags": account.tags,
            "watch_symbols": account.watch_symbols,
            "notes": account.notes,
        },
        "language": language,
        "preserve_english_summary": preserve_english_summary,
        "tweets": [
            {
                "tweet_id": tweet.tweet_id,
                "created_at": tweet.created_at.isoformat(),
                "text": tweet.text,
                "lang": tweet.lang,
                "url": tweet.url,
                "metrics": tweet.metrics.model_dump(mode="json"),
            }
            for tweet in tweets
        ],
        "required_json_schema": _account_report_schema(),
    }
    user_prompt = (
        "Analyze only the supplied tweets. The main report fields must be in Chinese. "
        "Keep english_source_summaries in English when possible. "
        "Return JSON only, without markdown fences.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_json_repair_messages(raw_response: str) -> list[dict[str, str]]:
    """Build a short repair prompt for invalid JSON responses."""

    return [
        {"role": "system", "content": "Return valid JSON only. Do not add explanations."},
        {
            "role": "user",
            "content": (
                "The following model response should be strict JSON matching the previous "
                "schema. Repair it and return JSON only:\n\n"
                f"{raw_response}"
            ),
        },
    ]


def _account_report_schema() -> dict[str, object]:
    return {
        "english_source_summaries": [
            {"tweet_id": "string", "summary": "short English summary"}
        ],
        "chinese_report": {
            "summary": "Chinese summary",
            "market_direction": "Chinese direction, e.g. 偏多/中性/偏谨慎",
            "key_themes": ["theme"],
            "mentioned_symbols": ["symbol"],
            "stock_watchlist": [
                {
                    "symbol": "symbol",
                    "direction": "Chinese direction",
                    "reason": "Chinese reason grounded in tweets",
                    "confidence": "low | medium | high",
                    "risk": "Chinese risk note or null",
                }
            ],
            "risk_notes": ["Chinese risk note"],
        },
    }
