"""Minimal CLI scaffold used by step 1 and extended in later steps."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Sequence

from trade_trend_kit.app.fetch_job import format_fetch_cycle_summary
from trade_trend_kit.app.services import DEFAULT_DATA_DIR, build_fake_fetch_job
from trade_trend_kit.config import DEFAULT_CONFIG_PATH, load_config, summarize_config
from trade_trend_kit.domain.errors import ConfigError
from trade_trend_kit.domain.models import RuntimeConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trade-trend-kit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run", help="Run the scheduled collector")
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
        print("trade-trend-kit: run mode is not implemented yet.")
        return 0
    if args.command == "fetch-once":
        if not args.fake:
            print("trade-trend-kit: fetch-once currently requires --fake until real adapters land.")
            return 2
        try:
            config = load_config(args.config)
        except ConfigError as exc:
            print(f"Config invalid: {exc}")
            return 1
        summary = asyncio.run(_run_fake_fetch_once(config=config, data_dir=args.data_dir))
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


async def _run_fake_fetch_once(config: RuntimeConfig, data_dir: Path):
    """Load config and execute one fake cycle behind the synchronous CLI."""

    job = build_fake_fetch_job(config=config, data_dir=data_dir)
    return await job.run_once(config)


if __name__ == "__main__":
    raise SystemExit(main())
