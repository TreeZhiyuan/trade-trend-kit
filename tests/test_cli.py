from __future__ import annotations

import json
from pathlib import Path

from trade_trend_kit.cli import build_parser, main


def test_cli_parser_accepts_validate_config() -> None:
    parser = build_parser()

    args = parser.parse_args(["validate-config", "--config", "custom.json"])

    assert args.command == "validate-config"
    assert args.config == Path("custom.json")


def test_validate_config_command_returns_zero_for_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    config_path.write_text(
        json.dumps(
            {
                "timezone": "Asia/Shanghai",
                "fetch_interval_minutes": 15,
                "tweet_limit": 10,
                "analysis_language": "zh-CN",
                "preserve_english_summary": True,
                "accounts": [],
            }
        ),
        encoding="utf-8",
    )

    assert main(["validate-config", "--config", str(config_path)]) == 0


def test_validate_config_command_returns_one_for_invalid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    config_path.write_text("[]", encoding="utf-8")

    assert main(["validate-config", "--config", str(config_path)]) == 1
