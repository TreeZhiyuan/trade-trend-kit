from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from trade_trend_kit.domain.models import DailyCandidateSymbol, DailyReport
from trade_trend_kit.infra.publishing.noop_publisher import NoopReportPublisher
from trade_trend_kit.infra.publishing.payloads import (
    build_daily_payload_id,
    build_daily_publish_payload,
    build_hashtags,
    render_social_excerpt,
)

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def fixed_time() -> datetime:
    return datetime(2026, 5, 23, 10, 0, tzinfo=PROJECT_TZ)


def make_daily_report() -> DailyReport:
    return DailyReport(
        date="2026-05-23",
        timezone="Asia/Shanghai",
        report_count=2,
        source_accounts=["macro_blogger", "tech_blogger"],
        source_tweet_ids=["1", "2"],
        market_overview="AI 资本开支仍是主要线索，但需要跟踪利率风险。",
        consensus_themes=["AI 资本开支", "利率风险"],
        conflicting_views=["成长股偏多与宏观谨慎并存。"],
        candidate_symbols=[
            DailyCandidateSymbol(
                symbol="NVDA",
                market="US_STOCK",
                direction="关注",
                reason="多位博主提到 AI 需求仍具韧性。",
                confidence="medium",
                risks=["估值较高"],
            )
        ],
        risk_events=["FOMC"],
        updated_at=fixed_time(),
    )


def test_build_daily_publish_payload_keeps_channel_neutral_fields() -> None:
    report = make_daily_report()

    payload = build_daily_publish_payload(report)

    assert payload.payload_id == build_daily_payload_id(report)
    assert payload.title == "2026-05-23 投资方向参考报告"
    assert payload.summary == report.market_overview
    assert payload.markdown_body.startswith("# 2026-05-23 投资方向参考报告")
    assert "市场概览：" in payload.plain_text_body
    assert payload.sections[0].heading == "市场概览"
    assert payload.sections[2].items[0].startswith("NVDA")
    assert payload.source_accounts == ["macro_blogger", "tech_blogger"]
    assert payload.candidate_symbols[0].symbol == "NVDA"


def test_build_hashtags_deduplicates_and_sanitizes_values() -> None:
    report = make_daily_report().model_copy(
        update={"consensus_themes": ["AI 资本开支", "AI 资本开支", "#利率-风险"]}
    )

    assert build_hashtags(report)[:4] == ["#投资参考", "#AI资本开支", "#利率风险", "#NVDA"]


def test_render_social_excerpt_caps_length() -> None:
    payload = build_daily_publish_payload(make_daily_report())

    excerpt = render_social_excerpt(payload, max_chars=40)

    assert len(excerpt) <= 40
    assert excerpt.endswith("…")


def test_noop_publisher_returns_successful_result() -> None:
    payload = build_daily_publish_payload(make_daily_report())
    publisher = NoopReportPublisher(channel="local-preview")

    result = asyncio.run(publisher.publish_daily_report(payload))

    assert result.success is True
    assert result.channel == "local-preview"
    assert result.external_id == payload.payload_id
