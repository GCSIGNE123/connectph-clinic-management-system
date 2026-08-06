"""Legacy Migration Wizard models (Phase 14).

These are process/meta tables for the import engine itself, not clinical
entities migrated *from* a legacy system - they do NOT carry `LegacyMixin`
(see migration 0014 docstring for the full reasoning). They do carry
`TenantMixin` (clinic-scoped) plus `created_at`/`updated_at` for
consistency with the rest of the project.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class MigrationSourceType(str, enum.Enum):
    SQLITE = "SQLite"
    ACCESS = "Access"
    SQLSERVER = "SQLServer"
    MYSQL = "MySQL"
    POSTGRESQL = "PostgreSQL"
    CSV = "CSV"
    EXCEL = "Excel"


class MigrationBatchStatus(str, enum.Enum):
    DRAFT = "Draft"
    CONNECTED = "Connected"
    ANALYZED = "Analyzed"
    PREVIEWED = "Previewed"
    VALIDATED = "Validated"
    IMPORTING = "Importing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    PARTIALLY_COMPLETED = "PartiallyCompleted"
    CANCELLED = "Cancelled"


class MigrationEntityType(str, enum.Enum):
    CLINIC = "Clinic"
    BRANCHES = "Branches"
    DEPARTMENTS = "Departments"
    DOCTORS = "Doctors"
    USERS = "Users"
    PATIENTS = "Patients"
    SERVICES = "Services"
    VISITS = "Visits"
    QUEUE_HISTORY = "QueueHistory"
    CONSULTATIONS = "Consultations"
    DIAGNOSES = "Diagnoses"
    PRESCRIPTIONS = "Prescriptions"
    LABORATORY = "Laboratory"
    BILLING = "Billing"
    PAYMENTS = "Payments"
    ATTACHMENTS = "Attachments"
    AUDIT_LOGS = "AuditLogs"


# The mandated 17-step import order - dependents must be imported after
# what they reference (e.g. Visits after Patients+Doctors).
MIGRATION_ENTITY_ORDER: list[MigrationEntityType] = [
    MigrationEntityType.CLINIC,
    MigrationEntityType.BRANCHES,
    MigrationEntityType.DEPARTMENTS,
    MigrationEntityType.DOCTORS,
    MigrationEntityType.USERS,
    MigrationEntityType.PATIENTS,
    MigrationEntityType.SERVICES,
    MigrationEntityType.VISITS,
    MigrationEntityType.QUEUE_HISTORY,
    MigrationEntityType.CONSULTATIONS,
    MigrationEntityType.DIAGNOSES,
    MigrationEntityType.PRESCRIPTIONS,
    MigrationEntityType.LABORATORY,
    MigrationEntityType.BILLING,
    MigrationEntityType.PAYMENTS,
    MigrationEntityType.ATTACHMENTS,
    MigrationEntityType.AUDIT_LOGS,
]


class MigrationEntityProgressStatus(str, enum.Enum):
    PENDING = "Pending"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    SKIPPED = "Skipped"


class MigrationTransformType(str, enum.Enum):
    NONE = "None"
    RENAME = "Rename"
    DATE_FORMAT = "DateFormat"
    PHONE_FORMAT = "PhoneFormat"
    TRIM = "Trim"
    CUSTOM = "Custom"


class MigrationIssueType(str, enum.Enum):
    REQUIRED_FIELD_MISSING = "RequiredFieldMissing"
    DUPLICATE_PATIENT = "DuplicatePatient"
    DUPLICATE_DOCTOR = "DuplicateDoctor"
    BROKEN_RELATIONSHIP = "BrokenRelationship"
    MISSING_FOREIGN_KEY = "MissingForeignKey"
    INVALID_DATE = "InvalidDate"
    INVALID_PHONE = "InvalidPhone"
    INVALID_EMAIL = "InvalidEmail"
    DUPLICATE_INVOICE_NUMBER = "DuplicateInvoiceNumber"
    DUPLICATE_VISIT_NUMBER = "DuplicateVisitNumber"


class MigrationIssueSeverity(str, enum.Enum):
    WARNING = "Warning"
    ERROR = "Error"


class MigrationIssueResolution(str, enum.Enum):
    UNRESOLVED = "Unresolved"
    SKIP = "Skip"
    MERGE = "Merge"
    OVERWRITE = "Overwrite"
    CREATE_NEW = "CreateNew"


class MigrationLogLevel(str, enum.Enum):
    INFO = "Info"
    WARNING = "Warning"
    ERROR = "Error"


class MigrationBatch(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migration_batches"

    source_type: Mapped[MigrationSourceType] = mapped_column(
        SAEnum(MigrationSourceType, name="migration_source_type", values_callable=_enum_values), nullable=False
    )
    source_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MigrationBatchStatus] = mapped_column(
        SAEnum(MigrationBatchStatus, name="migration_batch_status", values_callable=_enum_values),
        nullable=False, default=MigrationBatchStatus.DRAFT, server_default=MigrationBatchStatus.DRAFT.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    total_records_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_records_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_duplicates: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_warnings: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_entity: Mapped[MigrationEntityType | None] = mapped_column(
        SAEnum(MigrationEntityType, name="migration_entity_type", values_callable=_enum_values), nullable=True
    )
    uploaded_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    progress_rows: Mapped[list["MigrationEntityProgress"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MigrationBatch id={self.id} status={self.status!r}>"


class MigrationEntityProgress(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migration_entity_progress"

    migration_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[MigrationEntityType] = mapped_column(
        SAEnum(MigrationEntityType, name="migration_entity_type", values_callable=_enum_values), nullable=False
    )
    status: Mapped[MigrationEntityProgressStatus] = mapped_column(
        SAEnum(MigrationEntityProgressStatus, name="migration_entity_progress_status", values_callable=_enum_values),
        nullable=False, default=MigrationEntityProgressStatus.PENDING,
        server_default=MigrationEntityProgressStatus.PENDING.value,
    )
    records_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_imported: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_processed_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    batch: Mapped["MigrationBatch"] = relationship(back_populates="progress_rows")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MigrationEntityProgress batch={self.migration_batch_id} entity={self.entity_type!r}>"


class MigrationFieldMapping(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "migration_field_mappings"

    migration_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[MigrationEntityType] = mapped_column(
        SAEnum(MigrationEntityType, name="migration_entity_type", values_callable=_enum_values), nullable=False
    )
    source_field: Mapped[str] = mapped_column(String(200), nullable=False)
    destination_field: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transform_type: Mapped[MigrationTransformType] = mapped_column(
        SAEnum(MigrationTransformType, name="migration_transform_type", values_callable=_enum_values),
        nullable=False, default=MigrationTransformType.NONE, server_default=MigrationTransformType.NONE.value,
    )
    transform_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MigrationFieldMapping {self.source_field}->{self.destination_field}>"


class MigrationValidationIssue(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "migration_validation_issues"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    migration_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[MigrationEntityType] = mapped_column(
        SAEnum(MigrationEntityType, name="migration_entity_type", values_callable=_enum_values), nullable=False
    )
    source_row_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    issue_type: Mapped[MigrationIssueType] = mapped_column(
        SAEnum(MigrationIssueType, name="migration_issue_type", values_callable=_enum_values), nullable=False
    )
    severity: Mapped[MigrationIssueSeverity] = mapped_column(
        SAEnum(MigrationIssueSeverity, name="migration_issue_severity", values_callable=_enum_values), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[MigrationIssueResolution | None] = mapped_column(
        SAEnum(MigrationIssueResolution, name="migration_issue_resolution", values_callable=_enum_values),
        nullable=True,
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MigrationValidationIssue {self.issue_type!r} row={self.source_row_identifier}>"


class MigrationLog(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "migration_logs"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    migration_batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    log_level: Mapped[MigrationLogLevel] = mapped_column(
        SAEnum(MigrationLogLevel, name="migration_log_level", values_callable=_enum_values),
        nullable=False, default=MigrationLogLevel.INFO, server_default=MigrationLogLevel.INFO.value,
    )
    entity_type: Mapped[MigrationEntityType | None] = mapped_column(
        SAEnum(MigrationEntityType, name="migration_entity_type", values_callable=_enum_values), nullable=True
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MigrationLog {self.log_level!r} {self.message[:40]!r}>"
