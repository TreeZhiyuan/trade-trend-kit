"""JSON file IO helpers.

Every local persistence adapter should use these helpers so writes are atomic
and JSON formatting stays consistent across the project.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from trade_trend_kit.domain.errors import StorageError


def read_json_file(path: Path, default: Any | None = None) -> Any:
    """Read JSON from a file, returning `default` when the file is missing."""

    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise StorageError(f"Invalid JSON file: {path}: {exc}") from exc
    except OSError as exc:
        raise StorageError(f"Unable to read JSON file: {path}: {exc}") from exc


def write_json_file(path: Path, data: Any) -> None:
    """Atomically write JSON to a file."""

    text = json.dumps(data, ensure_ascii=False, indent=2)
    _write_text_atomic(path, f"{text}\n")


def write_text_file(path: Path, text: str) -> None:
    """Atomically write UTF-8 text to a file."""

    _write_text_atomic(path, text)


def append_jsonl_file(path: Path, rows: list[dict[str, Any]]) -> None:
    """Append JSON lines using an atomic rewrite."""

    if not rows:
        return

    existing_lines: list[str] = []
    if path.exists():
        try:
            existing_lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        except OSError as exc:
            raise StorageError(f"Unable to read JSONL file: {path}: {exc}") from exc

    new_lines = [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows]
    _write_text_atomic(path, "\n".join([*existing_lines, *new_lines]) + "\n")


def _write_text_atomic(path: Path, text: str) -> None:
    """Write text through a temp file in the same directory, then replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(path)
    except OSError as exc:
        raise StorageError(f"Unable to write JSON file: {path}: {exc}") from exc
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
