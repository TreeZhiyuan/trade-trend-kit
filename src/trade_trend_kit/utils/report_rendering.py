"""Markdown rendering for generated reports.

JSON remains the structured source of truth. Markdown is a push-friendly view
that can be reused by social/app publishers without coupling them to storage.
"""

from __future__ import annotations

from trade_trend_kit.domain.models import AccountIncrementalReport, DailyReport


def render_account_report_markdown(report: AccountIncrementalReport) -> str:
    """Render one account incremental report as concise Markdown."""

    chinese = report.chinese_report
    lines = [
        f"# {report.market} / {report.category} / @{report.account}",
        "",
        f"- 日期: {report.date}",
        f"- 新增推文: {report.new_tweet_count}",
        f"- 市场方向: {chinese.market_direction}",
        "",
        "## 中文分析",
        "",
        chinese.summary,
        "",
        "## 关键主题",
        "",
        *_render_bullets(chinese.key_themes),
        "",
        "## 关注标的",
        "",
        *_render_stock_watchlist(report),
        "",
        "## 英文原文摘要",
        "",
        *_render_english_summaries(report),
        "",
        "## 风险提示",
        "",
        *_render_bullets(chinese.risk_notes),
    ]
    return _normalize_markdown(lines)


def render_daily_report_markdown(report: DailyReport) -> str:
    """Render the daily aggregate report as concise Markdown."""

    lines = [
        f"# {report.date} 投资方向参考报告",
        "",
        f"- 时区: {report.timezone}",
        f"- 账号报告数: {report.report_count}",
        f"- 覆盖账号: {', '.join(report.source_accounts) or '-'}",
        "",
        "## 市场概览",
        "",
        report.market_overview,
        "",
        "## 共识主题",
        "",
        *_render_bullets(report.consensus_themes),
        "",
        "## 候选标的",
        "",
        *_render_daily_candidates(report),
        "",
        "## 分歧观点",
        "",
        *_render_bullets(report.conflicting_views),
        "",
        "## 风险事件",
        "",
        *_render_bullets(report.risk_events),
        "",
        "## 免责声明",
        "",
        report.disclaimer,
    ]
    return _normalize_markdown(lines)


def _render_stock_watchlist(report: AccountIncrementalReport) -> list[str]:
    rows = []
    for item in report.chinese_report.stock_watchlist:
        risk = f" 风险: {item.risk}" if item.risk else ""
        rows.append(
            f"- {item.symbol}: {item.direction}; 置信度: {item.confidence}; "
            f"理由: {item.reason}.{risk}"
        )
    return rows or ["- 暂无明确标的"]


def _render_english_summaries(report: AccountIncrementalReport) -> list[str]:
    rows = [
        f"- {summary.tweet_id}: {summary.summary}"
        for summary in report.english_source_summaries
    ]
    return rows or ["- 暂无英文摘要"]


def _render_daily_candidates(report: DailyReport) -> list[str]:
    rows = []
    for item in report.candidate_symbols:
        risks = f" 风险: {', '.join(item.risks)}" if item.risks else ""
        rows.append(
            f"- {item.symbol} ({item.market}): {item.direction}; "
            f"置信度: {item.confidence}; 理由: {item.reason}.{risks}"
        )
    return rows or ["- 暂无候选标的"]


def _render_bullets(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] or ["- 暂无"]


def _normalize_markdown(lines: list[str]) -> str:
    """Return Markdown with a single trailing newline."""

    return "\n".join(lines).rstrip() + "\n"
