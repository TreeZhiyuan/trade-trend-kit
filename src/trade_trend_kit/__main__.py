"""Allows `python -m trade_trend_kit` to use the same CLI as the script entry."""

from __future__ import annotations

from trade_trend_kit.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
