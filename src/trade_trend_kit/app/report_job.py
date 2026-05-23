"""Daily report aggregation orchestration.

Daily aggregation belongs in the application layer so it can be reused by the
scheduler, manual commands, and future push workflows.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from trade_trend_kit.domain.models import (
    AccountIncrementalReport,
    DailyCandidateSymbol,
    DailyReport,
)
from trade_trend_kit.utils.time import date_key, now_in_timezone


def build_daily_report(
    reports: Sequence[AccountIncrementalReport],
    timezone: str,
    generated_at: datetime | None = None,
) -> DailyReport:
    """Aggregate account-level reports produced in the current cycle."""

    report_items = list(reports)
    updated_at = generated_at or now_in_timezone(timezone)
    source_accounts = _unique(report.account for report in report_items)
    source_tweet_ids = _unique(
        tweet_id for report in report_items for tweet_id in report.source_tweet_ids
    )
    consensus_themes = _unique(
        theme
        for report in report_items
        for theme in report.chinese_report.key_themes
        if theme
    )
    risk_events = _unique(
        note
        for report in report_items
        for note in report.chinese_report.risk_notes
        if note
    )
    candidate_symbols = _build_candidate_symbols(report_items)
    directions = _unique(report.chinese_report.market_direction for report in report_items)

    return DailyReport(
        date=date_key(updated_at, timezone),
        timezone=timezone,
        report_count=len(report_items),
        source_accounts=source_accounts,
        source_tweet_ids=source_tweet_ids,
        market_overview=_build_market_overview(report_items, len(source_tweet_ids)),
        consensus_themes=consensus_themes,
        conflicting_views=_build_conflicting_views(directions),
        candidate_symbols=candidate_symbols,
        risk_events=risk_events,
        updated_at=updated_at,
    )


def _build_candidate_symbols(
    reports: Sequence[AccountIncrementalReport],
) -> list[DailyCandidateSymbol]:
    """Flatten account report watchlists into daily candidate symbols."""

    candidates: dict[tuple[str, str, str], DailyCandidateSymbol] = {}
    for report in reports:
        for item in report.chinese_report.stock_watchlist:
            key = (item.symbol.upper(), report.market, item.direction)
            existing = candidates.get(key)
            risks = [item.risk] if item.risk else []
            if existing:
                candidates[key] = existing.model_copy(
                    update={
                        "reason": f"{existing.reason}; {item.reason}",
                        "risks": _unique([*existing.risks, *risks]),
                    }
                )
                continue
            candidates[key] = DailyCandidateSymbol(
                symbol=item.symbol.upper(),
                market=report.market,
                direction=item.direction,
                reason=item.reason,
                confidence=item.confidence,
                risks=risks,
            )
    return list(candidates.values())


def _build_market_overview(
    reports: Sequence[AccountIncrementalReport],
    source_tweet_count: int,
) -> str:
    if not reports:
        return "本轮没有新增推文报告，暂不形成新的市场结论。"

    accounts = "、".join(_unique(report.account for report in reports))
    return (
        f"本轮 fake 流水线生成 {len(reports)} 份账号增量报告，"
        f"覆盖 {source_tweet_count} 条新增推文，来源账号包括 {accounts}。"
    )


def _build_conflicting_views(directions: list[str]) -> list[str]:
    if len(directions) <= 1:
        return []
    return [f"本轮账号观点存在差异，方向包括：{'、'.join(directions)}。"]


def _unique(values: Iterable[str]) -> list[str]:
    """Return non-empty strings in first-seen order."""

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
