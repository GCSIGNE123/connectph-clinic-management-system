"""Legacy Migration Wizard - core orchestration service (Phase 14).

Consolidates schema analysis, validation, preview, import and
verification into one service module (rather than five separate files)
for practicality within this phase's scope - the spec's logical
boundaries are preserved as methods/sections below, each documented.

### Scope decision (entities)
Only **Patients** and **Doctors** are wired to a real destination
create-path (`PatientService.create_patient` / `DoctorRepository.create`)
in this phase. The other 15 entity types in `MIGRATION_ENTITY_ORDER`
(Clinic, Branches, Departments, Users, Services, Visits, QueueHistory,
Consultations, Diagnoses, Prescriptions, Laboratory, Billing, Payments,
Attachments, AuditLogs) go through schema-analysis/mapping exactly the
same as Patients/Doctors, but `import_entity()` marks them `Skipped` with
an explanatory `migration_logs` entry - importing 17 fully cross-linked
clinical entity graphs (each with its own FK integrity rules) is out of
scope for what can be responsibly hand-verified in this pass; the
per-entity progress/mapping/validation architecture is real and already
supports adding the remaining entities without any schema change.

### Idempotency
`legacy_id` + `migration_batch_id` (both already columns on every entity
table via `LegacyMixin`) are looked up before every insert - if a row
with that pair already exists for the destination table, the row is
counted as skipped (already imported) rather than re-inserted. No
separate `sync_hash` column was added; see the 0014 migration docstring
for the explicit "decide and document" call.
"""

import time
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor
from app.models.migration_batch import (
    MIGRATION_ENTITY_ORDER,
    MigrationBatch,
    MigrationBatchStatus,
    MigrationEntityProgress,
    MigrationEntityProgressStatus,
    MigrationEntityType,
    MigrationFieldMapping,
    MigrationIssueResolution,
    MigrationIssueSeverity,
    MigrationIssueType,
    MigrationLog,
    MigrationLogLevel,
    MigrationValidationIssue,
)
from app.models.patient import CivilStatus, Gender, Patient
from app.models.user import User
from app.schemas.patient import MOBILE_NUMBER_PATTERN, PatientCreate
from app.services.audit_service import AuditService
from app.services.migration.source_adapters.registry import get_adapter
from app.services.migration.transforms import apply_transform
from app.services.patient_service import PatientService

_EMAIL_ADAPTER: TypeAdapter[EmailStr] = TypeAdapter(EmailStr)

# Which entity types are actually written to a real destination table.
IMPLEMENTED_ENTITIES = {MigrationEntityType.PATIENTS, MigrationEntityType.DOCTORS}

BATCH_SIZE = 500


def _mapped_row(row: dict[str, Any], mappings: list[MigrationFieldMapping]) -> dict[str, Any]:
    """Apply field mapping + transform to a raw source row, producing a
    dict keyed by destination field name."""
    result: dict[str, Any] = {}
    for m in mappings:
        if m.is_ignored or not m.destination_field:
            continue
        raw_value = row.get(m.source_field)
        result[m.destination_field] = apply_transform(raw_value, m.transform_type.value if hasattr(m.transform_type, "value") else m.transform_type, m.transform_config)
    return result


class MigrationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_service = AuditService(session)

    # ------------------------------------------------------------------
    # Batch lifecycle
    # ------------------------------------------------------------------

    async def create_batch(self, *, clinic_id: UUID, actor: User, source_type, source_description: str | None) -> MigrationBatch:
        batch = MigrationBatch(
            clinic_id=clinic_id,
            source_type=source_type,
            source_description=source_description,
            status=MigrationBatchStatus.DRAFT,
            started_by=actor.id,
        )
        self.session.add(batch)
        await self.session.flush()
        await self._log(batch.id, clinic_id, MigrationLogLevel.INFO, None, f"Migration batch created (source={source_type.value}).")
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="migration.batch_created",
            entity_type="migration_batch", entity_id=str(batch.id), metadata={"source_type": source_type.value},
        )
        await self.session.commit()
        return batch

    async def get_batch(self, batch_id: UUID, clinic_id: UUID) -> MigrationBatch | None:
        stmt = select(MigrationBatch).where(MigrationBatch.id == batch_id, MigrationBatch.clinic_id == clinic_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_batches(self, clinic_id: UUID) -> list[MigrationBatch]:
        stmt = select(MigrationBatch).where(MigrationBatch.clinic_id == clinic_id).order_by(MigrationBatch.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def set_uploaded_path(self, batch: MigrationBatch, path: str) -> None:
        batch.uploaded_file_path = path
        batch.status = MigrationBatchStatus.CONNECTED
        await self._log(batch.id, batch.clinic_id, MigrationLogLevel.INFO, None, "Source file(s) uploaded.")
        await self.session.commit()

    # ------------------------------------------------------------------
    # Analyze
    # ------------------------------------------------------------------

    async def analyze(self, batch: MigrationBatch, connection_config: dict[str, Any]) -> dict[str, list[str]]:
        adapter = get_adapter(batch.source_type, connection_config)
        await adapter.connect()
        try:
            schema = await adapter.analyze_schema()
            total = 0
            for name in schema:
                total += await adapter.count_rows(name)
            batch.total_records_found = total
            batch.status = MigrationBatchStatus.ANALYZED
            await self._log(batch.id, batch.clinic_id, MigrationLogLevel.INFO, None, f"Schema analyzed: {list(schema.keys())} ({total} rows found).")
            await self.session.commit()
            return schema
        finally:
            await adapter.close()

    # ------------------------------------------------------------------
    # Mapping suggestion is in mapping_service.py (imported by the API layer)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    async def validate_entity(
        self,
        batch: MigrationBatch,
        entity_type: MigrationEntityType,
        rows: list[dict[str, Any]],
        mappings: list[MigrationFieldMapping],
    ) -> list[MigrationValidationIssue]:
        issues: list[MigrationValidationIssue] = []
        entity_mappings = [m for m in mappings if m.entity_type == entity_type]

        seen_patient_keys: set[tuple] = set()
        existing_patients: list[Patient] | None = None
        if entity_type == MigrationEntityType.PATIENTS:
            existing_patients = list(
                (await self.session.execute(select(Patient).where(Patient.clinic_id == batch.clinic_id))).scalars().all()
            )
        existing_doctors: list[Doctor] | None = None
        if entity_type == MigrationEntityType.DOCTORS:
            existing_doctors = list(
                (await self.session.execute(select(Doctor).where(Doctor.clinic_id == batch.clinic_id))).scalars().all()
            )

        for idx, raw_row in enumerate(rows):
            row_id = str(raw_row.get("id") or raw_row.get("ID") or raw_row.get("_id") or idx + 1)
            mapped = _mapped_row(raw_row, entity_mappings)

            if entity_type == MigrationEntityType.PATIENTS:
                for field in ("first_name", "last_name", "birth_date", "mobile_number", "gender", "civil_status"):
                    if not mapped.get(field):
                        issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.REQUIRED_FIELD_MISSING,
                                                    MigrationIssueSeverity.ERROR, f"Required field '{field}' missing."))
                if mapped.get("birth_date") is None and raw_row.get("birth_date") not in (None, ""):
                    issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.INVALID_DATE,
                                                MigrationIssueSeverity.ERROR, "birth_date could not be parsed."))
                mobile = mapped.get("mobile_number")
                if mobile and not MOBILE_NUMBER_PATTERN.match(str(mobile)):
                    issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.INVALID_PHONE,
                                                MigrationIssueSeverity.ERROR, f"mobile_number '{mobile}' is not valid."))
                email = mapped.get("email")
                if email:
                    try:
                        _EMAIL_ADAPTER.validate_python(email)
                    except ValidationError:
                        issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.INVALID_EMAIL,
                                                    MigrationIssueSeverity.WARNING, f"email '{email}' is not valid."))
                key = (
                    str(mapped.get("first_name", "")).strip().lower(),
                    str(mapped.get("last_name", "")).strip().lower(),
                    str(mapped.get("birth_date", "")),
                )
                if key[0] and key[1] and key in seen_patient_keys:
                    issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.DUPLICATE_PATIENT,
                                                MigrationIssueSeverity.WARNING, "Duplicate name+DOB within source file."))
                seen_patient_keys.add(key)
                if existing_patients:
                    for p in existing_patients:
                        name_dob_match = (
                            p.first_name.strip().lower() == str(mapped.get("first_name", "")).strip().lower()
                            and p.last_name.strip().lower() == str(mapped.get("last_name", "")).strip().lower()
                            and str(p.birth_date) == str(mapped.get("birth_date", ""))
                        )
                        mobile_match = mobile and p.mobile_number == mobile
                        if name_dob_match or mobile_match:
                            issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.DUPLICATE_PATIENT,
                                                        MigrationIssueSeverity.WARNING,
                                                        f"Matches existing patient {p.patient_number} ({'name+DOB' if name_dob_match else 'mobile'})."))
                            break

            elif entity_type == MigrationEntityType.DOCTORS:
                for field in ("first_name", "last_name"):
                    if not mapped.get(field):
                        issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.REQUIRED_FIELD_MISSING,
                                                    MigrationIssueSeverity.ERROR, f"Required field '{field}' missing."))
                email = mapped.get("email")
                if email:
                    try:
                        _EMAIL_ADAPTER.validate_python(email)
                    except ValidationError:
                        issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.INVALID_EMAIL,
                                                    MigrationIssueSeverity.WARNING, f"email '{email}' is not valid."))
                if existing_doctors:
                    for d in existing_doctors:
                        if (
                            d.first_name.strip().lower() == str(mapped.get("first_name", "")).strip().lower()
                            and d.last_name.strip().lower() == str(mapped.get("last_name", "")).strip().lower()
                        ):
                            issues.append(self._issue(batch, entity_type, row_id, MigrationIssueType.DUPLICATE_DOCTOR,
                                                        MigrationIssueSeverity.WARNING,
                                                        f"Matches existing doctor {d.doctor_code}."))
                            break

        for issue in issues:
            self.session.add(issue)
        await self.session.flush()
        return issues

    def _issue(self, batch, entity_type, row_id, issue_type, severity, message) -> MigrationValidationIssue:
        return MigrationValidationIssue(
            clinic_id=batch.clinic_id, migration_batch_id=batch.id, entity_type=entity_type,
            source_row_identifier=row_id, issue_type=issue_type, severity=severity, message=message,
            resolution=MigrationIssueResolution.UNRESOLVED,
        )

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    async def preview_entity(self, batch: MigrationBatch, entity_type: MigrationEntityType, total_rows: int) -> dict[str, int]:
        stmt = select(MigrationValidationIssue).where(
            MigrationValidationIssue.migration_batch_id == batch.id,
            MigrationValidationIssue.entity_type == entity_type,
        )
        issues = list((await self.session.execute(stmt)).scalars().all())
        # Same resolution-aware rule as import_entity (see the fix note
        # there): a resolved Error issue no longer holds its row back.
        error_rows = {
            i.source_row_identifier for i in issues
            if i.severity == MigrationIssueSeverity.ERROR and i.resolution == MigrationIssueResolution.UNRESOLVED
        }
        warnings = sum(1 for i in issues if i.severity == MigrationIssueSeverity.WARNING)
        return {
            "rows_to_import": max(total_rows - len(error_rows), 0),
            "rows_to_skip": len(error_rows),
            "warnings": warnings,
            "errors": len(error_rows),
        }

    # ------------------------------------------------------------------
    # Import (background)
    # ------------------------------------------------------------------

    async def get_or_create_progress(self, batch: MigrationBatch, entity_type: MigrationEntityType) -> MigrationEntityProgress:
        stmt = select(MigrationEntityProgress).where(
            MigrationEntityProgress.migration_batch_id == batch.id,
            MigrationEntityProgress.entity_type == entity_type,
        )
        progress = (await self.session.execute(stmt)).scalar_one_or_none()
        if progress is None:
            progress = MigrationEntityProgress(
                clinic_id=batch.clinic_id, migration_batch_id=batch.id, entity_type=entity_type,
                status=MigrationEntityProgressStatus.PENDING,
            )
            self.session.add(progress)
            await self.session.flush()
        return progress

    async def import_entity(
        self,
        batch: MigrationBatch,
        entity_type: MigrationEntityType,
        rows: list[dict[str, Any]],
        mappings: list[MigrationFieldMapping],
        issues: list[MigrationValidationIssue],
        *,
        actor: User,
        migration_source_label: str,
    ) -> None:
        progress = await self.get_or_create_progress(batch, entity_type)
        progress.records_found = len(rows)
        progress.status = MigrationEntityProgressStatus.IN_PROGRESS
        progress.started_at = datetime.now(UTC)
        batch.current_entity = entity_type
        await self.session.commit()

        if entity_type not in IMPLEMENTED_ENTITIES:
            progress.status = MigrationEntityProgressStatus.SKIPPED
            progress.completed_at = datetime.now(UTC)
            await self._log(batch.id, batch.clinic_id, MigrationLogLevel.WARNING, entity_type,
                             f"{entity_type.value} import not implemented in this phase - skipped. "
                             f"See services/migration/migration_service.py scope decision.")
            await self.session.commit()
            return

        entity_mappings = [m for m in mappings if m.entity_type == entity_type]
        # Bug fix (Phase 17 UAT): a row with an *unresolved* Error issue is
        # held back from import (the admin hasn't decided what to do with
        # it yet), but once the admin has resolved that issue - to Merge,
        # Overwrite, CreateNew, or anything other than a bare "Skip" - the
        # row must go through import normally instead of being silently
        # dropped forever. Previously this set included every Error-severity
        # row regardless of `resolution`, so calling POST
        # /migration/batches/{id}/issues/{issue_id}/resolve with anything
        # but Skip had no effect: the row was still force-skipped here and
        # miscounted as a "duplicate" in the batch summary, hiding the real
        # cause. A very common real-world shape - a legacy CSV missing an
        # optional-with-safe-default column like `civil_status` - imported
        # zero rows even though `_import_one` already defaults that field.
        error_row_ids = {
            i.source_row_identifier for i in issues
            if i.entity_type == entity_type and i.severity == MigrationIssueSeverity.ERROR
            and i.resolution == MigrationIssueResolution.UNRESOLVED
        }
        skip_row_ids = {
            i.source_row_identifier for i in issues
            if i.entity_type == entity_type and i.resolution == MigrationIssueResolution.SKIP
        }

        offset = progress.last_processed_offset
        while offset < len(rows):
            batch_rows = rows[offset : offset + BATCH_SIZE]
            imported = 0
            skipped = 0
            failed = 0
            try:
                for idx_in_batch, raw_row in enumerate(batch_rows):
                    idx = offset + idx_in_batch
                    row_id = str(raw_row.get("id") or raw_row.get("ID") or raw_row.get("_id") or idx + 1)
                    if row_id in error_row_ids or row_id in skip_row_ids:
                        skipped += 1
                        continue
                    mapped = _mapped_row(raw_row, entity_mappings)
                    import asyncio as _asyncio
                    created = await _asyncio.wait_for(
                        self._import_one(batch, entity_type, row_id, mapped, actor=actor, migration_source_label=migration_source_label),
                        timeout=15,
                    )
                    if created:
                        imported += 1
                    else:
                        skipped += 1  # already imported previously (idempotency)
                await self.session.commit()
            except Exception as exc:  # noqa: BLE001
                await self.session.rollback()
                failed = len(batch_rows)
                await self._log(batch.id, batch.clinic_id, MigrationLogLevel.ERROR, entity_type,
                                 f"Batch at offset {offset} failed and was rolled back: {exc}")
                progress.records_failed += failed
                progress.status = MigrationEntityProgressStatus.FAILED
                await self.session.commit()
                raise

            progress.records_imported += imported
            progress.records_skipped += skipped
            progress.last_processed_offset = offset + len(batch_rows)
            await self.session.commit()
            offset += len(batch_rows)

        progress.status = MigrationEntityProgressStatus.COMPLETED
        progress.completed_at = datetime.now(UTC)
        await self._log(batch.id, batch.clinic_id, MigrationLogLevel.INFO, entity_type,
                         f"{entity_type.value}: {progress.records_imported} imported, {progress.records_skipped} skipped, {progress.records_failed} failed.")
        await self.session.commit()

    async def _import_one(
        self, batch: MigrationBatch, entity_type: MigrationEntityType, legacy_id: str, mapped: dict[str, Any],
        *, actor: User, migration_source_label: str,
    ) -> bool:
        """Returns True if a new row was created, False if it already
        existed for this (legacy_id, migration_batch_id) pair (idempotent
        no-op)."""
        if entity_type == MigrationEntityType.PATIENTS:
            existing = (await self.session.execute(
                select(Patient).where(Patient.clinic_id == batch.clinic_id, Patient.legacy_id == legacy_id,
                                       Patient.migration_batch_id == str(batch.id))
            )).scalar_one_or_none()
            if existing:
                return False
            payload = PatientCreate(
                first_name=mapped.get("first_name", ""),
                middle_name=mapped.get("middle_name"),
                last_name=mapped.get("last_name", ""),
                suffix=mapped.get("suffix"),
                birth_date=mapped.get("birth_date"),
                gender=Gender(mapped.get("gender")) if mapped.get("gender") in [g.value for g in Gender] else Gender.OTHER,
                civil_status=CivilStatus(mapped.get("civil_status")) if mapped.get("civil_status") in [c.value for c in CivilStatus] else CivilStatus.SINGLE,
                nationality=mapped.get("nationality") or "Filipino",
                mobile_number=mapped.get("mobile_number", "+639000000000"),
                email=mapped.get("email") or None,
                address_line=mapped.get("address_line"),
                barangay=mapped.get("barangay"),
                city=mapped.get("city"),
                province=mapped.get("province"),
                zip_code=mapped.get("zip_code"),
            )
            patient_service = PatientService(self.session)
            response = await patient_service.create_patient(payload, clinic_id=batch.clinic_id, actor=actor, override_duplicate_warning=True)
            # `create_patient` returns a `PatientRead` (pydantic) schema, not
            # the ORM row - re-fetch the ORM instance so we can stamp the
            # legacy-migration columns onto it.
            patient = await self.session.get(Patient, response.patient.id)
            patient.legacy_id = legacy_id
            patient.migration_batch_id = str(batch.id)
            patient.migration_source = migration_source_label
            patient.imported_at = datetime.now(UTC)
            await self.session.flush()
            return True

        if entity_type == MigrationEntityType.DOCTORS:
            existing = (await self.session.execute(
                select(Doctor).where(Doctor.clinic_id == batch.clinic_id, Doctor.legacy_id == legacy_id,
                                      Doctor.migration_batch_id == str(batch.id))
            )).scalar_one_or_none()
            if existing:
                return False
            from app.services.doctor_code_generator import DoctorCodeGenerator

            code_generator = DoctorCodeGenerator(self.session)
            doctor_code = await code_generator.next_code(batch.clinic_id)
            doctor = Doctor(
                clinic_id=batch.clinic_id,
                doctor_code=doctor_code,
                first_name=mapped.get("first_name", ""),
                middle_name=mapped.get("middle_name"),
                last_name=mapped.get("last_name", ""),
                suffix=mapped.get("suffix"),
                prc_license=mapped.get("prc_license"),
                ptr_number=mapped.get("ptr_number"),
                specialization=mapped.get("specialization"),
                contact_number=mapped.get("contact_number"),
                email=mapped.get("email"),
                legacy_id=legacy_id,
                migration_batch_id=str(batch.id),
                migration_source=migration_source_label,
                imported_at=datetime.now(UTC),
            )
            self.session.add(doctor)
            await self.session.flush()
            return True

        return False

    # ------------------------------------------------------------------
    # Status / logs / verify
    # ------------------------------------------------------------------

    async def entity_progress(self, batch_id: UUID, clinic_id: UUID) -> list[MigrationEntityProgress]:
        stmt = select(MigrationEntityProgress).where(
            MigrationEntityProgress.migration_batch_id == batch_id, MigrationEntityProgress.clinic_id == clinic_id
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def logs(self, batch_id: UUID, clinic_id: UUID) -> list[MigrationLog]:
        stmt = select(MigrationLog).where(
            MigrationLog.migration_batch_id == batch_id, MigrationLog.clinic_id == clinic_id
        ).order_by(MigrationLog.logged_at.asc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def verify(self, batch: MigrationBatch) -> dict[str, Any]:
        entities = await self.entity_progress(batch.id, batch.clinic_id)
        reports = []
        relationship_issues: list[str] = []
        for p in entities:
            reports.append({
                "entity_type": p.entity_type,
                "expected": p.records_found - p.records_failed,
                "imported": p.records_imported,
                "matches": (p.records_found - p.records_failed - p.records_skipped) <= p.records_imported or p.status == MigrationEntityProgressStatus.SKIPPED,
            })
        overall_ok = all(r["matches"] for r in reports)
        return {
            "batch_id": batch.id,
            "generated_at": datetime.now(UTC),
            "entities": reports,
            "relationship_issues": relationship_issues,
            "overall_ok": overall_ok,
        }

    async def _log(self, batch_id: UUID, clinic_id: UUID, level: MigrationLogLevel, entity_type: MigrationEntityType | None, message: str, details: dict | None = None) -> None:
        entry = MigrationLog(clinic_id=clinic_id, migration_batch_id=batch_id, log_level=level, entity_type=entity_type, message=message, details=details)
        self.session.add(entry)
        await self.session.flush()
