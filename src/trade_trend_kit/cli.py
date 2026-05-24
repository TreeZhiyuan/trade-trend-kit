"""Minimal CLI scaffold used by step 1 and extended in later steps."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Sequence

from trade_trend_kit.app.fetch_job import format_fetch_cycle_summary
from trade_trend_kit.app.services import (
    DEFAULT_DATA_DIR,
    build_fake_fetch_job,
    build_twikit_fetch_job,
)
from trade_trend_kit.config import DEFAULT_CONFIG_PATH, load_config, summarize_config
from trade_trend_kit.domain.errors import ConfigError, TradeTrendKitError
from trade_trend_kit.domain.models import RuntimeConfig
from trade_trend_kit.logging_config import configure_logging
from trade_trend_kit.scheduler import ScheduledRunSettings, run_scheduled_collector
from trade_trend_kit.utils.env import load_env_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trade-trend-kit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the scheduled collector")
    run_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config JSON. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    run_parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Local runtime data directory. Defaults to {DEFAULT_DATA_DIR}.",
    )
    run_parser.add_argument(
        "--fake",
        action="store_true",
        help="Run the deterministic local fake pipeline instead of real integrations.",
    )
    run_parser.add_argument(
        "--twikit",
        action="store_true",
        help="Fetch real X posts through Twikit.",
    )
    run_parser.add_argument(
        "--llm",
        action="store_true",
        help="Use the OpenAI-compatible analyzer instead of the fake analyzer.",
    )
    run_parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to environment file with credentials. Defaults to .env.",
    )
    run_parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Override LOG_LEVEL for console logging.",
    )
    run_parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Write logs to this file in addition to stderr.",
    )
    fetch_once_parser = subparsers.add_parser("fetch-once", help="Run one collection cycle")
    fetch_once_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config JSON. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    fetch_once_parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Local runtime data directory. Defaults to {DEFAULT_DATA_DIR}.",
    )
    fetch_once_parser.add_argument(
        "--fake",
        action="store_true",
        help="Run the deterministic local fake pipeline instead of real integrations.",
    )
    fetch_once_parser.add_argument(
        "--twikit",
        action="store_true",
        help="Fetch real X posts through Twikit.",
    )
    fetch_once_parser.add_argument(
        "--llm",
        action="store_true",
        help="Use the OpenAI-compatible analyzer instead of the fake analyzer.",
    )
    fetch_once_parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Path to environment file with Twikit credentials. Defaults to .env.",
    )
    fetch_once_parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Override LOG_LEVEL for console logging.",
    )
    fetch_once_parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Write logs to this file in addition to stderr.",
    )
    validate_parser = subparsers.add_parser("validate-config", help="Validate config/x.json")
    validate_parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config JSON. Defaults to {DEFAULT_CONFIG_PATH}.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        load_env_file(args.env_file)
        configure_logging(args.log_level, args.log_file)
        if args.fake == args.twikit:
            print("trade-trend-kit: run requires exactly one mode: --fake or --twikit.")
            return 2
        settings = ScheduledRunSettings(
            config_path=args.config,
            data_dir=args.data_dir,
            env_file=args.env_file,
            source="fake" if args.fake else "twikit",
            use_llm_analyzer=args.llm,
        )
        try:
            asyncio.run(run_scheduled_collector(settings))
        except KeyboardInterrupt:
            return 0
        except TradeTrendKitError as exc:
            print(f"Run failed: {exc}")
            return 1
        return 0
    if args.command == "fetch-once":
        load_env_file(args.env_file)
        configure_logging(args.log_level, args.log_file)
        if args.fake == args.twikit:
            print("trade-trend-kit: fetch-once requires exactly one mode: --fake or --twikit.")
            return 2
        try:
            config = load_config(args.config)
            if args.fake:
                summary = asyncio.run(
                    _run_fake_fetch_once(
                        config=config,
                        data_dir=args.data_dir,
                        env_file=args.env_file,
                        use_llm_analyzer=args.llm,
                    )
                )
            else:
                summary = asyncio.run(
                    _run_twikit_fetch_once(
                        config=config,
                        data_dir=args.data_dir,
                        env_file=args.env_file,
                        use_llm_analyzer=args.llm,
                    )
                )
        except ConfigError as exc:
            print(f"Config invalid: {exc}")
            return 1
        except TradeTrendKitError as exc:
            print(f"Run failed: {exc}")
            return 1
        print(format_fetch_cycle_summary(summary))
        return 0
    if args.command == "validate-config":
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"Config invalid: {exc}")
            return 1
        print(summarize_config(config))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


async def _run_fake_fetch_once(config: RuntimeConfig, data_dir: Path, env_file: Path, use_llm_analyzer: bool):
    """Load config and execute one fake cycle behind the synchronous CLI."""

    job = build_fake_fetch_job(
        config=config,
        data_dir=data_dir,
        env_file=env_file,
        use_llm_analyzer=use_llm_analyzer,
    )
    return await job.run_once(config)


async def _run_twikit_fetch_once(config: RuntimeConfig, data_dir: Path, env_file: Path, use_llm_analyzer: bool):
    """Load config and execute one Twikit-backed cycle behind the synchronous CLI."""

    job = build_twikit_fetch_job(
        config=config,
        data_dir=data_dir,
        env_file=env_file,
        use_llm_analyzer=use_llm_analyzer,
    )
    return await job.run_once(config)


if __name__ == "__main__":
    raise SystemExit(main())
