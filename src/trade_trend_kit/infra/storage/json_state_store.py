"""Local JSON runtime state repository adapter."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from trade_trend_kit.domain.errors import StorageError
from trade_trend_kit.domain.models import RuntimeState
from trade_trend_kit.domain.ports import StateRepository
from trade_trend_kit.utils.json_io import read_json_file, write_json_file

DEFAULT_STATE_PATH = Path("data/runtime/state.json")


class JsonStateRepository(StateRepository):
    """Store runtime state in a single JSON file."""

    def __init__(self, path: Path | str = DEFAULT_STATE_PATH) -> None:
        self.path = Path(path)

    async def load(self) -> RuntimeState:
        """Load runtime state or return an empty state when none exists."""

        raw_state = read_json_file(self.path, default={})
        if not raw_state:
            return RuntimeState()
        try:
            return RuntimeState.model_validate(raw_state)
        except ValidationError as exc:
            raise StorageError(f"Invalid runtime state file: {self.path}: {exc}") from exc

    async def save(self, state: RuntimeState) -> None:
        """Persist runtime state atomically."""

        write_json_file(self.path, state.model_dump(mode="json"))
