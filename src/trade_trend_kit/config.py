"""Configuration loading and validation entry points.

The CLI and application services should use this module instead of reading
`config/x.json` directly. That keeps config validation behavior consistent
across manual commands, scheduled runs, and tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from trade_trend_kit.domain.errors import ConfigError
from trade_trend_kit.domain.models import RuntimeConfig

DEFAULT_CONFIG_PATH = Path("config/x.json")
EXAMPLE_CONFIG_PATH = Path("config/x.example.json")


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> RuntimeConfig:
    """Load and validate runtime configuration from a JSON file."""

    config_path = Path(path)
    raw_config = read_config_json(config_path)
    return parse_config(raw_config, source=config_path)


def read_config_json(path: Path) -> dict[str, Any]:
    """Read config JSON and normalize file/JSON errors into ConfigError."""

    if not path.exists():
        example_hint = f" Copy {EXAMPLE_CONFIG_PATH} to {DEFAULT_CONFIG_PATH} first."
        raise ConfigError(f"Config file not found: {path}.{example_hint}")
    if not path.is_file():
        raise ConfigError(f"Config path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Unable to read config file: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config root must be a JSON object: {path}")
    return data


def parse_config(data: dict[str, Any], source: Path | None = None) -> RuntimeConfig:
    """Validate already-loaded config data as a RuntimeConfig model."""

    try:
        return RuntimeConfig.model_validate(data)
    except ValidationError as exc:
        location = f" from {source}" if source else ""
        details = format_validation_error(exc)
        raise ConfigError(f"Invalid config{location}: {details}") from exc


def format_validation_error(error: ValidationError) -> str:
    """Turn Pydantic errors into compact CLI-friendly messages."""

    messages: list[str] = []
    for item in error.errors():
        loc = ".".join(str(part) for part in item["loc"]) or "config"
        messages.append(f"{loc}: {item['msg']}")
    return "; ".join(messages)


def summarize_config(config: RuntimeConfig) -> str:
    """Build a short human-readable summary for successful validation."""

    enabled_accounts = [account for account in config.accounts if account.enabled]
    disabled_accounts = [account for account in config.accounts if not account.enabled]
    return (
        "Config valid: "
        f"timezone={config.timezone}, "
        f"interval={config.fetch_interval_minutes}m, "
        f"tweet_limit={config.tweet_limit}, "
        f"accounts={len(config.accounts)}, "
        f"enabled={len(enabled_accounts)}, "
        f"disabled={len(disabled_accounts)}"
    )
