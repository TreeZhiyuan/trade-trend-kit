"""Scheduler entry points.

The scheduler will stay thin: it should trigger application services, not hold
business logic itself. That keeps scheduled and one-shot execution consistent.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from trade_trend_kit.app.fetch_job import FetchCycleSummary, format_fetch_cycle_summary
from trade_trend_kit.app.services import (
    DEFAULT_DATA_DIR,
    build_fake_fetch_job,
    build_twikit_fetch_job,
)
from trade_trend_kit.config import DEFAULT_CONFIG_PATH, load_config
from trade_trend_kit.domain.errors import ConfigError
from trade_trend_kit.domain.models import RuntimeConfig
from trade_trend_kit.utils.time import get_timezone, now_in_timezone

LOGGER = logging.getLogger(__name__)
SCHEDULED_JOB_ID = "trade-trend-kit-fetch-cycle"
RunSource = Literal["fake", "twikit"]
CycleRunner = Callable[["ScheduledRunSettings"], Awaitable[FetchCycleSummary]]


@dataclass(frozen=True)
class ScheduledRunSettings:
    """User-selected runtime settings shared by scheduled and one-shot runs."""

    config_path: Path = DEFAULT_CONFIG_PATH
    data_dir: Path = DEFAULT_DATA_DIR
    env_file: Path = Path(".env")
    source: RunSource = "twikit"
    use_llm_analyzer: bool = False
    run_immediately: bool = True


class ScheduledCollector:
    """Own the APScheduler job and protect cycles from overlapping."""

    def __init__(
        self,
        settings: ScheduledRunSettings,
        scheduler: AsyncIOScheduler | None = None,
        cycle_runner: CycleRunner | None = None,
        clock: Callable[[str], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.scheduler = scheduler
        self.cycle_runner = cycle_runner or run_collection_once
        self.clock = clock or now_in_timezone
        self._cycle_lock = asyncio.Lock()
        self._scheduled_signature: tuple[int, str] | None = None

    def configure(self, config: RuntimeConfig) -> object:
        """Add or replace the interval job without starting the scheduler."""

        scheduler = self._ensure_scheduler(config)
        self._scheduled_signature = (config.fetch_interval_minutes, config.timezone)
        job_kwargs = {}
        if self.settings.run_immediately:
            job_kwargs["next_run_time"] = self.clock(config.timezone)

        return scheduler.add_job(
            self._safe_run_cycle,
            trigger=IntervalTrigger(
                minutes=config.fetch_interval_minutes,
                timezone=get_timezone(config.timezone),
            ),
            id=SCHEDULED_JOB_ID,
            name="trade-trend-kit fetch/analyze cycle",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
            **job_kwargs,
        )

    def start(self) -> None:
        """Load config once for schedule settings, then start the scheduler."""

        config = load_config(self.settings.config_path)
        self.configure(config)
        scheduler = self._ensure_scheduler(config)
        scheduler.start()
        LOGGER.info(
            "Scheduled collector started: interval=%sm source=%s llm=%s",
            config.fetch_interval_minutes,
            self.settings.source,
            self.settings.use_llm_analyzer,
        )

    def shutdown(self, wait: bool = True) -> None:
        """Stop the scheduler without interrupting an already running cycle."""

        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=wait)

    async def run_cycle(self) -> FetchCycleSummary | None:
        """Run one cycle unless a previous cycle is still active."""

        if self._cycle_lock.locked():
            LOGGER.warning("Skipping scheduled cycle because a previous cycle is still running.")
            return None

        async with self._cycle_lock:
            return await self.cycle_runner(self.settings)

    async def _safe_run_cycle(self) -> None:
        """Log scheduled-cycle failures and keep the scheduler alive."""

        try:
            summary = await self.run_cycle()
        except Exception:  # noqa: BLE001 - scheduled jobs must not kill the loop.
            LOGGER.exception("Scheduled collection cycle failed.")
            return

        try:
            config = load_config(self.settings.config_path)
        except ConfigError:
            LOGGER.exception("Unable to reload config after a scheduled cycle.")
            return

        self._maybe_refresh_schedule(config)
        if summary is not None:
            LOGGER.info("\n%s", format_fetch_cycle_summary(summary))

    def _ensure_scheduler(self, config: RuntimeConfig) -> AsyncIOScheduler:
        if self.scheduler is None:
            self.scheduler = AsyncIOScheduler(timezone=get_timezone(config.timezone))
        return self.scheduler

    def _maybe_refresh_schedule(self, config: RuntimeConfig) -> None:
        """Reschedule when interval or timezone changes on disk."""

        new_signature = (config.fetch_interval_minutes, config.timezone)
        if new_signature == self._scheduled_signature:
            return
        scheduler = self._ensure_scheduler(config)
        scheduler.reschedule_job(
            SCHEDULED_JOB_ID,
            trigger=IntervalTrigger(
                minutes=config.fetch_interval_minutes,
                timezone=get_timezone(config.timezone),
            ),
        )
        self._scheduled_signature = new_signature
        LOGGER.info(
            "Rescheduled collector: interval=%sm timezone=%s",
            config.fetch_interval_minutes,
            config.timezone,
        )


async def run_collection_once(settings: ScheduledRunSettings) -> FetchCycleSummary:
    """Load the latest config and execute one collection cycle."""

    config = load_config(settings.config_path)
    job = _build_fetch_job(settings=settings, config=config)
    return await job.run_once(config)


async def run_scheduled_collector(settings: ScheduledRunSettings) -> None:
    """Start scheduled collection and block until cancelled or interrupted."""

    collector = ScheduledCollector(settings=settings)
    collector.start()
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    finally:
        collector.shutdown()


def _build_fetch_job(settings: ScheduledRunSettings, config: RuntimeConfig):
    if settings.source == "fake":
        return build_fake_fetch_job(
            config=config,
            data_dir=settings.data_dir,
            env_file=settings.env_file,
            use_llm_analyzer=settings.use_llm_analyzer,
        )
    if settings.source == "twikit":
        return build_twikit_fetch_job(
            config=config,
            data_dir=settings.data_dir,
            env_file=settings.env_file,
            use_llm_analyzer=settings.use_llm_analyzer,
        )
    raise ConfigError(f"Unsupported run source: {settings.source}")
