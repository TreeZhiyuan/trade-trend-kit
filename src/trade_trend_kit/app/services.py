"""Application service assembly.

Concrete adapters are composed here so CLI and scheduler entry points stay
thin. Step 5 intentionally wires fake adapters first; replacing them with
Twikit/OpenAI-compatible adapters should not change the app orchestration.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from trade_trend_kit.app.fetch_job import FetchAndAnalyzeJob
from trade_trend_kit.domain.models import RuntimeConfig
from trade_trend_kit.infra.fake.analyzer import FakeTweetAnalyzer
from trade_trend_kit.infra.fake.x_client import FakeXPostClient
from trade_trend_kit.infra.storage.json_report_store import JsonReportRepository
from trade_trend_kit.infra.storage.json_state_store import JsonStateRepository
from trade_trend_kit.infra.storage.json_tweet_store import JsonTweetRepository
from trade_trend_kit.utils.time import now_in_timezone

DEFAULT_DATA_DIR = Path("data")


def build_fake_fetch_job(
    config: RuntimeConfig,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    clock: Callable[[str], datetime] | None = None,
) -> FetchAndAnalyzeJob:
    """Build a full local pipeline using deterministic fake integrations."""

    root = Path(data_dir)
    job_clock = clock or now_in_timezone
    fixed_now = job_clock(config.timezone)
    return FetchAndAnalyzeJob(
        x_client=FakeXPostClient(timezone=config.timezone, fixed_now=fixed_now),
        tweet_repository=JsonTweetRepository(
            raw_dir=root / "raw_tweets",
            normalized_dir=root / "normalized_tweets",
            timezone=config.timezone,
        ),
        state_repository=JsonStateRepository(root / "runtime" / "state.json"),
        analyzer=FakeTweetAnalyzer(timezone=config.timezone, fixed_now=fixed_now),
        report_repository=JsonReportRepository(root / "reports"),
        clock=job_clock,
    )
