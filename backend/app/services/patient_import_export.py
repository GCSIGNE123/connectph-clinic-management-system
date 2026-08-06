"""Extension points for future patient import/export functionality.

Only interfaces are defined here (per Phase 3 scope) - no CSV/Excel/legacy
importer or exporter is implemented yet. A future phase should implement a
concrete subclass of `PatientImporter` / `PatientExporter` and wire it up
behind a new `api/v1/patients_import_export.py` router (or additional
endpoints on `api/v1/patients.py`).
"""

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID


class PatientImporter(ABC):
    """Abstract base for bulk-importing patients from an external source.

    Implementations are expected to:
      - validate rows against `schemas.patient.PatientCreate`,
      - run duplicate detection per row (see `PatientService.check_duplicates`),
      - return a structured report of created/skipped/failed rows rather than
        raising on the first bad row, so an admin can review partial imports.
    """

    @abstractmethod
    async def import_from_csv(self, clinic_id: UUID, file_bytes: bytes, *, actor_id: UUID) -> dict[str, Any]:
        """Import patients from a CSV file. Returns an import report."""
        raise NotImplementedError

    @abstractmethod
    async def import_from_excel(self, clinic_id: UUID, file_bytes: bytes, *, actor_id: UUID) -> dict[str, Any]:
        """Import patients from an .xlsx workbook. Returns an import report."""
        raise NotImplementedError

    @abstractmethod
    async def import_from_legacy(self, clinic_id: UUID, source_config: dict[str, Any], *, actor_id: UUID) -> dict[str, Any]:
        """Import patients from the legacy Windows desktop app's data store
        (e.g. a legacy DB export or file dump). Should populate
        `legacy_patient_id` / `legacy_meta` on each created row so future
        reconciliation is possible. Returns an import report."""
        raise NotImplementedError


class PatientExporter(ABC):
    """Abstract base for exporting the patient roster to common formats."""

    @abstractmethod
    async def export_to_csv(self, clinic_id: UUID, *, filters: dict[str, Any] | None = None) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def export_to_excel(self, clinic_id: UUID, *, filters: dict[str, Any] | None = None) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def export_to_pdf(self, clinic_id: UUID, *, filters: dict[str, Any] | None = None) -> bytes:
        raise NotImplementedError
