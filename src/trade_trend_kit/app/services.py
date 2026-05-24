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
from trade_trend_kit.domain.ports import TweetAnalyzer
from trade_trend_kit.infra.fake.analyzer import FakeTweetAnalyzer
from trade_trend_kit.infra.fake.x_client import FakeXPostClient
from trade_trend_kit.infra.llm.error_archive import JsonLLMErrorArchive
from trade_trend_kit.infra.llm.openai_compatible import (
    OpenAICompatibleAnalyzer,
    OpenAICompatibleSettings,
)
from trade_trend_kit.infra.storage.json_report_store import JsonReportRepository
from trade_trend_kit.infra.storage.json_state_store import JsonStateRepository
from trade_trend_kit.infra.storage.json_tweet_store import JsonTweetRepository
from trade_trend_kit.infra.x.twikit_client import TwikitSettings, TwikitXPostClient
from trade_trend_kit.utils.time import now_in_timezone

DEFAULT_DATA_DIR = Path("data")


def build_fake_fetch_job(
    config: RuntimeConfig,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    env_file: str | Path = Path(".env"),
    use_llm_analyzer: bool = False,
    clock: Callable[[str], datetime] | None = None,
) -> FetchAndAnalyzeJob:
    """Build a full local pipeline using deterministic fake integrations."""

    root = Path(data_dir)
    reports_dir = root / "reports"
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
        analyzer=_build_tweet_analyzer(
            config=config,
            env_file=env_file,
            use_llm_analyzer=use_llm_analyzer,
            clock=job_clock,
            fixed_now=fixed_now,
            reports_dir=reports_dir,
        ),
        report_repository=JsonReportRepository(reports_dir),
        clock=job_clock,
    )


def build_twikit_fetch_job(
    config: RuntimeConfig,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    env_file: str | Path = Path(".env"),
    use_llm_analyzer: bool = False,
    clock: Callable[[str], datetime] | None = None,
) -> FetchAndAnalyzeJob:
    """Build a pipeline that fetches real X posts through Twikit."""

    root = Path(data_dir)
    reports_dir = root / "reports"
    job_clock = clock or now_in_timezone
    fixed_now = job_clock(config.timezone)
    twikit_settings = TwikitSettings.from_env(
        env_file=env_file,
        default_cookies_path=root / "runtime" / "cookies.json",
        timezone=config.timezone,
    )
    return FetchAndAnalyzeJob(
        x_client=TwikitXPostClient(settings=twikit_settings),
        tweet_repository=JsonTweetRepository(
            raw_dir=root / "raw_tweets",
            normalized_dir=root / "normalized_tweets",
            timezone=config.timezone,
        ),
        state_repository=JsonStateRepository(root / "runtime" / "state.json"),
        analyzer=_build_tweet_analyzer(
            config=config,
            env_file=env_file,
            use_llm_analyzer=use_llm_analyzer,
            clock=job_clock,
            fixed_now=fixed_now,
            reports_dir=reports_dir,
        ),
        report_repository=JsonReportRepository(reports_dir),
        clock=job_clock,
    )


def _build_tweet_analyzer(
    config: RuntimeConfig,
    env_file: str | Path,
    use_llm_analyzer: bool,
    clock: Callable[[str], datetime],
    fixed_now: datetime,
    reports_dir: Path,
) -> TweetAnalyzer:
    """Choose the analysis adapter without leaking provider details to the CLI."""

    if use_llm_analyzer:
        settings = OpenAICompatibleSettings.from_env(
            env_file=env_file,
            timezone=config.timezone,
            language=config.analysis_language,
            preserve_english_summary=config.preserve_english_summary,
        )
        return OpenAICompatibleAnalyzer(
            settings=settings,
            clock=clock,
            error_archive=JsonLLMErrorArchive(reports_dir),
        )
    return FakeTweetAnalyzer(timezone=config.timezone, fixed_now=fixed_now)
