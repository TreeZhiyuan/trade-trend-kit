from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from trade_trend_kit.domain.models import (
    AccountIncrementalReport,
    ChineseAccountReport,
    DailyReport,
    EnglishSourceSummary,
)
from trade_trend_kit.utils.report_rendering import (
    render_account_report_markdown,
    render_daily_report_markdown,
)

PROJECT_TZ = ZoneInfo("Asia/Shanghai")


def fixed_time() -> datetime:
    return datetime(2026, 5, 23, 10, 0, tzinfo=PROJECT_TZ)


def test_render_account_report_markdown_keeps_chinese_and_english_sections() -> None:
    report = AccountIncrementalReport(
        report_id="report-1",
        date="2026-05-23",
        account="macro_blogger",
        market="US_STOCK",
        category="macro",
        new_tweet_count=1,
        source_tweet_ids=["1"],
        english_source_summaries=[
            EnglishSourceSummary(tweet_id="1", summary="Liquidity remains supportive.")
        ],
        chinese_report=ChineseAccountReport(
            summary="新增推文偏多。",
            market_direction="偏多",
            key_themes=["liquidity"],
            risk_notes=["需要更多来源确认。"],
        ),
        created_at=fixed_time(),
    )

    markdown = render_account_report_markdown(report)

    assert markdown.startswith("# US_STOCK / macro / @macro_blogger")
    assert "## 中文分析" in markdown
    assert "## 英文原文摘要" in markdown
    assert "Liquidity remains supportive." in markdown


def test_render_daily_report_markdown_includes_disclaimer() -> None:
    report = DailyReport(
        date="2026-05-23",
        timezone="Asia/Shanghai",
        report_count=1,
        source_accounts=["macro_blogger"],
        source_tweet_ids=["1"],
        market_overview="整体偏谨慎。",
        updated_at=fixed_time(),
    )

    markdown = render_daily_report_markdown(report)

    assert markdown.startswith("# 2026-05-23 投资方向参考报告")
    assert "## 市场概览" in markdown
    assert report.disclaimer in markdown
