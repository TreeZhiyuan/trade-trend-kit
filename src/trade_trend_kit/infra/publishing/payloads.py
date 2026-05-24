"""Build push-ready payloads from daily reports.

This module does not send anything externally. It prepares stable JSON,
Markdown, and plain-text views that future social-platform or app publishers
can consume without parsing report storage internals.
"""

from __future__ import annotations

import re
from datetime import datetime

from trade_trend_kit.domain.models import DailyReport, PublishPayload, PublishSection
from trade_trend_kit.utils.filenames import build_file_stem
from trade_trend_kit.utils.report_rendering import render_daily_report_markdown

MAX_HASHTAGS = 8
MARKDOWN_DECORATION_PATTERN = re.compile(r"^[#*\-\s]+")
WHITESPACE_PATTERN = re.compile(r"\s+")


def build_daily_publish_payload(
    report: DailyReport,
    created_at: datetime | None = None,
) -> PublishPayload:
    """Create the channel-neutral payload used by future push adapters."""

    markdown_body = render_daily_report_markdown(report)
    sections = _build_sections(report)
    title = f"{report.date} 投资方向参考报告"
    return PublishPayload(
        payload_id=build_daily_payload_id(report),
        report_date=report.date,
        timezone=report.timezone,
        title=title,
        summary=report.market_overview,
        markdown_body=markdown_body,
        plain_text_body=render_plain_text_body(report, title),
        sections=sections,
        hashtags=build_hashtags(report),
        source_accounts=list(report.source_accounts),
        source_tweet_ids=list(report.source_tweet_ids),
        candidate_symbols=list(report.candidate_symbols),
        risk_events=list(report.risk_events),
        disclaimer=report.disclaimer,
        created_at=created_at or report.updated_at,
    )


def build_daily_payload_id(report: DailyReport) -> str:
    """Build a stable id from report date and updated timestamp."""

    return build_file_stem("daily_payload", report.date, report.updated_at.isoformat())


def render_plain_text_body(report: DailyReport, title: str | None = None) -> str:
    """Render a social-platform friendly plain-text body."""

    heading = title or f"{report.date} 投资方向参考报告"
    lines = [
        heading,
        "",
        f"市场概览：{report.market_overview}",
        "",
        "共识主题：",
        *_prefix_items(report.consensus_themes),
        "",
        "候选标的：",
        *_prefix_items(_candidate_lines(report)),
        "",
        "风险事件：",
        *_prefix_items(report.risk_events),
        "",
        report.disclaimer,
    ]
    return "\n".join(line.rstrip() for line in lines).strip() + "\n"


def render_social_excerpt(payload: PublishPayload, max_chars: int = 500) -> str:
    """Return a short excerpt that later publishers can post directly."""

    text = WHITESPACE_PATTERN.sub(" ", payload.plain_text_body).strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1].rstrip()}…"


def build_hashtags(report: DailyReport) -> list[str]:
    """Build conservative hashtags from report themes, symbols, and market names."""

    raw_tags = [
        "投资参考",
        *report.consensus_themes,
        *(candidate.symbol for candidate in report.candidate_symbols),
        *(candidate.market for candidate in report.candidate_symbols),
    ]
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in raw_tags:
        normalized = _normalize_hashtag(raw_tag)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tags.append(f"#{normalized}")
        if len(tags) >= MAX_HASHTAGS:
            break
    return tags


def _build_sections(report: DailyReport) -> list[PublishSection]:
    return [
        PublishSection(
            heading="市场概览",
            body=report.market_overview,
        ),
        PublishSection(
            heading="共识主题",
            items=list(report.consensus_themes),
        ),
        PublishSection(
            heading="候选标的",
            items=_candidate_lines(report),
        ),
        PublishSection(
            heading="分歧观点",
            items=list(report.conflicting_views),
        ),
        PublishSection(
            heading="风险事件",
            items=list(report.risk_events),
        ),
        PublishSection(
            heading="免责声明",
            body=report.disclaimer,
        ),
    ]


def _candidate_lines(report: DailyReport) -> list[str]:
    lines = []
    for candidate in report.candidate_symbols:
        risks = f"；风险：{', '.join(candidate.risks)}" if candidate.risks else ""
        lines.append(
            f"{candidate.symbol}（{candidate.market}）：{candidate.direction}，"
            f"置信度 {candidate.confidence}，理由：{candidate.reason}{risks}"
        )
    return lines


def _prefix_items(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items] or ["- 暂无"]


def _normalize_hashtag(value: str) -> str:
    text = MARKDOWN_DECORATION_PATTERN.sub("", value).strip()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
    return text[:30]
