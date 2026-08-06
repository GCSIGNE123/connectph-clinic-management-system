"""Architecture-only stub adapters for database source types not yet
implemented (SQLite/Access/SQL Server/MySQL/PostgreSQL). Each implements
the `SourceAdapter` interface shape but raises `NotImplementedError` on
`connect()`, pointing operators at the CSV/Excel export path as the
current recommended route until a specific client's database technology
is identified and prioritized.
"""

from collections.abc import AsyncIterator
from typing import Any

_MESSAGE = (
    "{label} source adapter is not yet implemented in this build. Export your "
    "legacy data to CSV or Excel and use the CSV/Excel adapter instead - see "
    "docs/MIGRATION.md for the expected column structure per entity."
)


class _StubAdapter:
    label = "This"

    def __init__(self, connection_config: dict[str, Any]) -> None:
        self.connection_config = connection_config

    async def connect(self) -> None:
        raise NotImplementedError(_MESSAGE.format(label=self.label))

    async def analyze_schema(self) -> dict[str, list[str]]:
        raise NotImplementedError(_MESSAGE.format(label=self.label))

    async def read_table(
        self, name: str, *, batch_size: int = 500, offset: int = 0
    ) -> AsyncIterator[list[dict[str, Any]]]:
        raise NotImplementedError(_MESSAGE.format(label=self.label))
        yield  # pragma: no cover

    async def close(self) -> None:
        return None


class SqliteSourceAdapter(_StubAdapter):
    label = "SQLite"


class AccessSourceAdapter(_StubAdapter):
    label = "Microsoft Access"


class SqlServerSourceAdapter(_StubAdapter):
    label = "SQL Server"


class MySqlSourceAdapter(_StubAdapter):
    label = "MySQL"


class PostgresSourceAdapter(_StubAdapter):
    label = "PostgreSQL"
