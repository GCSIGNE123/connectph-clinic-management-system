"""Abstract source adapter interface for the Legacy Migration Wizard.

Every legacy database technology (SQLite/Access/SQL Server/MySQL/
PostgreSQL) as well as flat-file exports (CSV/Excel) implements this same
four-method contract so the rest of the migration engine (schema
analyzer, mapping/validation/import services) never needs to know which
concrete source it is talking to.

Only `CsvSourceAdapter` and `ExcelSourceAdapter` are fully implemented in
this phase (see `docs/MIGRATION.md` / `docs/DATABASE.md` for the scope
decision - CSV/Excel cover "export from virtually any legacy desktop
system" without a specific client's database technology being known
yet). The database adapters are architecture-only stubs that raise
`NotImplementedError` pointing back at the CSV/Excel path.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class SourceAdapter(ABC):
    """Base class every migration source adapter must implement."""

    def __init__(self, connection_config: dict[str, Any]) -> None:
        self.connection_config = connection_config
        self._connected = False

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection / load the file. Raises on failure."""

    @abstractmethod
    async def analyze_schema(self) -> dict[str, list[str]]:
        """Return {table_or_sheet_name: [column_names]} for the source."""

    @abstractmethod
    async def read_table(
        self, name: str, *, batch_size: int = 500, offset: int = 0
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Yield successive batches of rows (as dicts) from a table/sheet,
        starting at `offset`, for streaming/resumable reads."""
        raise NotImplementedError
        yield  # pragma: no cover - makes this an async generator

    @abstractmethod
    async def close(self) -> None:
        """Release any held resources (file handles, DB connections)."""

    async def count_rows(self, name: str) -> int:
        """Default naive implementation - concrete adapters may override
        with a cheaper source-native count."""
        total = 0
        async for batch in self.read_table(name, batch_size=1000):
            total += len(batch)
        return total
