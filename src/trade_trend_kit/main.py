"""Compatibility entry point for running the package as a module."""

from __future__ import annotations

from trade_trend_kit.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
