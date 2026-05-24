from __future__ import annotations

import logging
from pathlib import Path

from trade_trend_kit.logging_config import configure_logging


def test_configure_logging_writes_to_optional_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "trade-trend-kit.log"

    configure_logging("INFO", log_file=log_file)
    logging.getLogger("trade_trend_kit.test").info("diagnostic event")
    logging.shutdown()

    assert "diagnostic event" in log_file.read_text(encoding="utf-8")
