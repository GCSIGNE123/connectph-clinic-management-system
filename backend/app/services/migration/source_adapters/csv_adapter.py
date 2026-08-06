"""CSV source adapter - fully implemented (stdlib `csv` only, no extra
dependency). One uploaded CSV file == one entity/table. The wizard's
"Choose Source" step, for CSV, lets the operator upload one file per
entity type they want to import (e.g. `patients.csv`, `doctors.csv`)."""

import csv
import io
from collections.abc import AsyncIterator
from typing import Any


class CsvSourceAdapter:
    """Reads a single CSV file's rows in batches.

    `connection_config` expects `{"files": {entity_type: file_path_or_bytes}}`
    where each value is either a filesystem path (str) or raw bytes content.
    """

    def __init__(self, connection_config: dict[str, Any]) -> None:
        self.connection_config = connection_config
        self._connected = False
        self._rows_cache: dict[str, list[dict[str, Any]]] = {}

    async def connect(self) -> None:
        files = self.connection_config.get("files", {})
        for name, source in files.items():
            self._rows_cache[name] = self._load_rows(source)
        self._connected = True

    @staticmethod
    def _load_rows(source: Any) -> list[dict[str, Any]]:
        if isinstance(source, (bytes, bytearray)):
            text = source.decode("utf-8-sig")
        else:
            with open(source, encoding="utf-8-sig") as fh:
                text = fh.read()
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]

    async def analyze_schema(self) -> dict[str, list[str]]:
        return {name: (list(rows[0].keys()) if rows else []) for name, rows in self._rows_cache.items()}

    async def read_table(
        self, name: str, *, batch_size: int = 500, offset: int = 0
    ) -> AsyncIterator[list[dict[str, Any]]]:
        rows = self._rows_cache.get(name, [])
        for start in range(offset, len(rows), batch_size):
            yield rows[start : start + batch_size]

    async def count_rows(self, name: str) -> int:
        return len(self._rows_cache.get(name, []))

    async def close(self) -> None:
        self._rows_cache.clear()
        self._connected = False
