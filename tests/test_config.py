from __future__ import annotations

import json
from pathlib import Path

import pytest

from trade_trend_kit.config import load_config, parse_config, summarize_config
from trade_trend_kit.domain.errors import ConfigError


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def valid_config_data() -> dict[str, object]:
    return {
        "timezone": "Asia/Shanghai",
        "fetch_interval_minutes": 15,
        "tweet_limit": 10,
        "analysis_language": "zh-CN",
        "preserve_english_summary": True,
        "accounts": [
            {
                "account": "@example_user",
                "display_name": "Example Analyst",
                "enabled": True,
                "market": "US_STOCK",
                "category": "macro",
                "region": "US",
                "tags": ["macro"],
                "priority": 1,
                "watch_symbols": ["SPY"],
            }
        ],
    }


def test_load_config_reads_and_validates_json_file(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    write_json(config_path, valid_config_data())

    config = load_config(config_path)

    assert config.timezone == "Asia/Shanghai"
    assert config.accounts[0].account == "example_user"
    assert config.accounts[0].file_key == "US_STOCK_macro_example_user"


def test_load_config_raises_config_error_for_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.json"

    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(missing_path)


def test_load_config_raises_config_error_for_invalid_json(tmp_path: Path) -> None:
    config_path = tmp_path / "x.json"
    config_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config(config_path)


def test_parse_config_rejects_duplicate_accounts() -> None:
    data = valid_config_data()
    data["accounts"] = [
        {"account": "example_user", "market": "US_STOCK", "category": "macro"},
        {"account": "@Example_User", "market": "US_STOCK", "category": "macro"},
    ]

    with pytest.raises(ConfigError, match="duplicate account configured"):
        parse_config(data)


def test_parse_config_rejects_invalid_numeric_settings() -> None:
    data = valid_config_data()
    data["tweet_limit"] = 0

    with pytest.raises(ConfigError, match="tweet_limit"):
        parse_config(data)


def test_summarize_config_includes_account_counts() -> None:
    config = parse_config(valid_config_data())

    summary = summarize_config(config)

    assert "accounts=1" in summary
    assert "enabled=1" in summary
    assert "disabled=0" in summary
