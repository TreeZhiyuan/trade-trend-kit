"""No-op report publisher used by the MVP.

The publishing port exists from the start, but this adapter intentionally does
nothing until real social platform or app delivery channels are added.
"""

from __future__ import annotations

from trade_trend_kit.domain.models import PublishPayload, PublishResult
from trade_trend_kit.domain.ports import ReportPublisher


class NoopReportPublisher(ReportPublisher):
    """Pretend to publish a payload while keeping tests and local runs offline."""

    def __init__(self, channel: str = "noop") -> None:
        self.channel = channel

    async def publish_daily_report(self, payload: PublishPayload) -> PublishResult:
        """Return a successful publish result without external side effects."""

        return PublishResult(
            channel=self.channel,
            success=True,
            message=f"Prepared payload {payload.payload_id}; external publishing disabled.",
            external_id=payload.payload_id,
        )
