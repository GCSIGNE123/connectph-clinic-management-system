"""Legacy Migration Wizard (Phase 14).

This is the payoff for the `LegacyMixin` columns (`legacy_id`,
`migration_batch_id`, `migration_source`, `legacy_created_at`,
`legacy_updated_at`, `imported_at`) that every entity table has carried
since Phase 5 - this phase does NOT add migration columns to entity
tables (they already exist), it adds the tables needed to *run* an
import: batches, per-entity progress (for resume), field mappings,
validation issues, and an operational log.

Idempotency decision: entity tables already have `legacy_id` (source PK)
+ `migration_batch_id`. That pair is sufficient to detect "this source
row was already imported" without a separate `sync_hash` column on every
entity table - the import service looks up
`WHERE legacy_id = :id AND migration_batch_id = :batch_id` before
inserting. We do NOT add a `sync_hash` column to entity tables. We do
add `content_hash` to `migration_entity_progress` batches-processed
bookkeeping is unnecessary since `legacy_id` lookups are enough; kept out
per the "decide and document" instruction in the spec.

Legacy-mixin-on-meta-tables decision: `migration_batches` and its four
child tables are the migration tracking system itself, not clinical/
business entities migrated *from* a legacy system, so they do NOT get
`LegacyMixin`. They do get `TenantMixin` (clinic-scoped) and
`created_at`/`updated_at` for consistency with every other table in the
project.

Revision ID: 0014_legacy_migration_wizard
Revises: 0013_tv_queue_display
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_legacy_migration_wizard"
down_revision: str | None = "0013_tv_queue_display"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _add_legacy_columns(table_name: str) -> None:
    """Add the standard `LegacyMixin` columns to a table that predates
    this phase's audit and was found to be missing them (`branches`,
    `departments`, `doctors`, `services`) - additive/nullable,
    matching the approach every other entity table already used since
    Phase 5's `0005_reception_queue` migration."""
    op.add_column(table_name, sa.Column("legacy_id", sa.String(64), nullable=True))
    op.create_index(f"ix_{table_name}_legacy_id", table_name, ["legacy_id"])
    op.add_column(table_name, sa.Column("legacy_meta", postgresql.JSONB(), nullable=True))
    op.add_column(table_name, sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("migration_batch_id", sa.String(64), nullable=True))
    op.create_index(f"ix_{table_name}_migration_batch_id", table_name, ["migration_batch_id"])
    op.add_column(table_name, sa.Column("migration_source", sa.String(100), nullable=True))
    op.add_column(table_name, sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True))


def upgrade() -> None:
    # Audit found four entity tables (branches, departments, doctors,
    # services) that were missing the `LegacyMixin` columns every
    # other entity table already carries - backfill them now, additively,
    # before building the import engine that depends on them.
    for table_name in ("branches", "departments", "doctors", "services"):
        _add_legacy_columns(table_name)

    migration_source_type = sa.Enum(
        "SQLite", "Access", "SQLServer", "MySQL", "PostgreSQL", "CSV", "Excel",
        name="migration_source_type",
    )
    migration_batch_status = sa.Enum(
        "Draft", "Connected", "Analyzed", "Previewed", "Validated", "Importing",
        "Completed", "Failed", "PartiallyCompleted", "Cancelled",
        name="migration_batch_status",
    )
    migration_entity_type = sa.Enum(
        "Clinic", "Branches", "Departments", "Doctors", "Users", "Patients",
        "Services", "Visits", "QueueHistory", "Consultations", "Diagnoses",
        "Prescriptions", "Laboratory", "Billing", "Payments", "Attachments",
        "AuditLogs",
        name="migration_entity_type",
    )
    migration_entity_progress_status = sa.Enum(
        "Pending", "InProgress", "Completed", "Failed", "Skipped",
        name="migration_entity_progress_status",
    )
    migration_transform_type = sa.Enum(
        "None", "Rename", "DateFormat", "PhoneFormat", "Trim", "Custom",
        name="migration_transform_type",
    )
    migration_issue_type = sa.Enum(
        "RequiredFieldMissing", "DuplicatePatient", "DuplicateDoctor",
        "BrokenRelationship", "MissingForeignKey", "InvalidDate", "InvalidPhone",
        "InvalidEmail", "DuplicateInvoiceNumber", "DuplicateVisitNumber",
        name="migration_issue_type",
    )
    migration_issue_severity = sa.Enum("Warning", "Error", name="migration_issue_severity")
    migration_issue_resolution = sa.Enum(
        "Unresolved", "Skip", "Merge", "Overwrite", "CreateNew",
        name="migration_issue_resolution",
    )
    migration_log_level = sa.Enum("Info", "Warning", "Error", name="migration_log_level")

    op.create_table(
        "migration_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("source_type", migration_source_type, nullable=False),
        sa.Column("source_description", sa.Text(), nullable=True),
        sa.Column("status", migration_batch_status, nullable=False, server_default="Draft"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("total_records_found", sa.Integer(), nullable=True),
        sa.Column("total_records_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duplicates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_warnings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_entity", migration_entity_type, nullable=True),
        sa.Column("uploaded_file_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "migration_entity_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("migration_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_type", migration_entity_type, nullable=False),
        sa.Column("status", migration_entity_progress_status, nullable=False, server_default="Pending"),
        sa.Column("records_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_processed_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("migration_batch_id", "entity_type", name="uq_migration_entity_progress_batch_entity"),
    )

    op.create_table(
        "migration_field_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("migration_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_type", migration_entity_type, nullable=False),
        sa.Column("source_field", sa.String(200), nullable=False),
        sa.Column("destination_field", sa.String(200), nullable=True),
        sa.Column("transform_type", migration_transform_type, nullable=False, server_default="None"),
        sa.Column("transform_config", postgresql.JSONB(), nullable=True),
        sa.Column("is_ignored", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "migration_validation_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("migration_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity_type", migration_entity_type, nullable=False),
        sa.Column("source_row_identifier", sa.String(200), nullable=False),
        sa.Column("issue_type", migration_issue_type, nullable=False),
        sa.Column("severity", migration_issue_severity, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolution", migration_issue_resolution, nullable=True),
        sa.Column("resolved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "migration_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("migration_batch_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("migration_batches.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("log_level", migration_log_level, nullable=False, server_default="Info"),
        sa.Column("entity_type", migration_entity_type, nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def _drop_legacy_columns(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_migration_batch_id", table_name=table_name)
    op.drop_column(table_name, "imported_at")
    op.drop_column(table_name, "migration_source")
    op.drop_column(table_name, "migration_batch_id")
    op.drop_column(table_name, "legacy_updated_at")
    op.drop_column(table_name, "legacy_created_at")
    op.drop_column(table_name, "legacy_meta")
    op.drop_index(f"ix_{table_name}_legacy_id", table_name=table_name)
    op.drop_column(table_name, "legacy_id")


def downgrade() -> None:
    op.drop_table("migration_logs")
    op.drop_table("migration_validation_issues")
    op.drop_table("migration_field_mappings")
    op.drop_table("migration_entity_progress")
    op.drop_table("migration_batches")

    for enum_name in (
        "migration_log_level",
        "migration_issue_resolution",
        "migration_issue_severity",
        "migration_issue_type",
        "migration_transform_type",
        "migration_entity_progress_status",
        "migration_entity_type",
        "migration_batch_status",
        "migration_source_type",
    ):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)

    for table_name in ("branches", "departments", "doctors", "services"):
        _drop_legacy_columns(table_name)
