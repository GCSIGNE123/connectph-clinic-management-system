"""Adapter registry - looks up the correct `SourceAdapter` implementation
by `MigrationSourceType`. Adding a new adapter is a one-line registration
here plus a new module implementing the `SourceAdapter` interface."""

from typing import Any

from app.models.migration_batch import MigrationSourceType
from app.services.migration.source_adapters.csv_adapter import CsvSourceAdapter
from app.services.migration.source_adapters.excel_adapter import ExcelSourceAdapter
from app.services.migration.source_adapters.stubs import (
    AccessSourceAdapter,
    MySqlSourceAdapter,
    PostgresSourceAdapter,
    SqliteSourceAdapter,
    SqlServerSourceAdapter,
)

_REGISTRY = {
    MigrationSourceType.CSV: CsvSourceAdapter,
    MigrationSourceType.EXCEL: ExcelSourceAdapter,
    MigrationSourceType.SQLITE: SqliteSourceAdapter,
    MigrationSourceType.ACCESS: AccessSourceAdapter,
    MigrationSourceType.SQLSERVER: SqlServerSourceAdapter,
    MigrationSourceType.MYSQL: MySqlSourceAdapter,
    MigrationSourceType.POSTGRESQL: PostgresSourceAdapter,
}

# The only source types with a real, working implementation in this phase.
FULLY_IMPLEMENTED_SOURCE_TYPES = {MigrationSourceType.CSV, MigrationSourceType.EXCEL}


def get_adapter(source_type: MigrationSourceType, connection_config: dict[str, Any]):
    adapter_cls = _REGISTRY.get(source_type)
    if adapter_cls is None:
        raise ValueError(f"No adapter registered for source type {source_type!r}")
    return adapter_cls(connection_config)
