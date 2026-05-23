from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_trend_kit.cli import build_parser, main
from trade_trend_kit.utils.json_io import read_json_file


def test_cli_parser_accepts_validate_config() -> None:
    parser = build_parser()

    args = parser.parse_args(["validate-config", "--config", "custom.json"])

    assert args.command == "validate-config"
    assert args.config == Path("custom.json")


def test_cli_parser_accepts_fake_fetch_once_options() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "fetch-once",
            "--fake",
            "--llm",
            "--config",
            "custom.json",
            "--data-dir",
            "runtime-data",
            "--env-file",
            ".env.local",
        ]
    )

    assert args.command == "fetch-once"
    assert args.fake is True
    assert args.llm is True
    assert args.config == Path("custom.json")
    assert args.data_dir == Path("runtime-data")
    assert args.env_file == Path(".env.local")


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


def test_fetch_once_requires_fake_flag() -> None:
    assert main(["fetch-once"]) == 2


def test_fetch_once_llm_requires_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    config_path = tmp_path / "x.json"
    env_path = tmp_path / ".env"
    config_path.write_text(
        json.dumps(
            {
                "timezone": "Asia/Shanghai",
                "fetch_interval_minutes": 15,
                "tweet_limit": 1,
                "analysis_language": "zh-CN",
                "preserve_english_summary": True,
                "accounts": [],
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text("LLM_API_KEY=\n", encoding="utf-8")

    exit_code = main(
        [
            "fetch-once",
            "--fake",
            "--llm",
            "--config",
            str(config_path),
            "--env-file",
            str(env_path),
        ]
    )

    assert exit_code == 1


def test_fetch_once_fake_command_generates_local_runtime_data(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    data_dir = tmp_path / "data"
    config_path.write_text(
        json.dumps(
            {
                "timezone": "Asia/Shanghai",
                "fetch_interval_minutes": 15,
                "tweet_limit": 2,
                "analysis_language": "zh-CN",
                "preserve_english_summary": True,
                "accounts": [
                    {
                        "account": "cli_blogger",
                        "display_name": "CLI Blogger",
                        "enabled": True,
                        "market": "US_STOCK",
                        "category": "macro",
                        "tags": ["fed"],
                        "watch_symbols": ["SPY"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "fetch-once",
            "--fake",
            "--config",
            str(config_path),
            "--data-dir",
            str(data_dir),
        ]
    )

    assert exit_code == 0
    state = read_json_file(data_dir / "runtime" / "state.json")
    assert len(state["accounts"]["cli_blogger"]["analyzed_tweet_ids"]) == 2
