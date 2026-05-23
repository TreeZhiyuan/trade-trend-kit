"""Minimal CLI scaffold used by step 1 and extended in later steps."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trade-trend-kit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run", help="Run the scheduled collector")
    subparsers.add_parser("fetch-once", help="Run one collection cycle")
    subparsers.add_parser("validate-config", help="Validate config/x.json")

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
        # Step 1 only checks whether the expected config files exist.
        config_path = Path("config/x.json")
        example_path = Path("config/x.example.json")
        if config_path.exists():
            print(f"Config found: {config_path}")
        elif example_path.exists():
            print(f"Config not found, example available at: {example_path}")
        else:
            print("No config file found.")
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
