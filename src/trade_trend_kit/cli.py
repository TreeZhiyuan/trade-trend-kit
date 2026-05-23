"""Minimal CLI scaffold used by step 1 and extended in later steps."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from trade_trend_kit.config import DEFAULT_CONFIG_PATH, load_config, summarize_config
from trade_trend_kit.domain.errors import ConfigError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trade-trend-kit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run", help="Run the scheduled collector")
    subparsers.add_parser("fetch-once", help="Run one collection cycle")
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
        print("trade-trend-kit: fetch-once mode is not implemented yet.")
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


if __name__ == "__main__":
    raise SystemExit(main())
