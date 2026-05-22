from __future__ import annotations

from trade_trend_kit.cli import build_parser, main


def test_cli_parser_accepts_validate_config() -> None:
    parser = build_parser()

    args = parser.parse_args(["validate-config"])

    assert args.command == "validate-config"


def test_validate_config_command_is_scaffolded() -> None:
    assert main(["validate-config"]) == 0
