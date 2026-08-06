"""Doctor Workspace (Phase 7).

Adds:
- `users.doctor_id` (nullable FK to `doctors`) - resolves a logged-in
  Doctor-role User to their Doctor record, needed for "Doctors may only
  view Visits assigned to them" filtering.
- `consultation_sessions` - one row per Start->Complete Consultation span,
  used to compute real "average consultation time" dashboard stats.
- `visit_locks` - "who currently has this Visit open for editing" - see
  `app/models/visit_lock.py` for the acquisition/release/expiry design.
- `doctor_activity` - domain-specific doctor action log feeding the
  Doctor Dashboard's stat cards (mirrors how `visit_timeline_events`
  relates to the generic `audit_logs` table).

Revision ID: 0007_doctor_workspace
Revises: 0006_visit_management
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_doctor_workspace"
down_revision: str | None = "0006_visit_management"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    consultation_session_status_enum = postgresql.ENUM(
        "Active", "Ended", name="consultation_session_status", create_type=False,
    )
    consultation_session_status_enum.create(bind, checkfirst=True)

    doctor_activity_type_enum = postgresql.ENUM(
        "PatientCalled", "PatientRecalled", "ConsultationStarted", "ConsultationCompleted",
        "MarkedNoShow", "VisitCancelled", "VisitOpened",
        name="doctor_activity_type", create_type=False,
    )
    doctor_activity_type_enum.create(bind, checkfirst=True)

    # --- users.doctor_id (additive, nullable) ---
    op.add_column(
        "users",
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_users_doctor_id", "users", ["doctor_id"])

    # --- consultation_sessions ---
    op.create_table(
        "consultation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("status", consultation_session_status_enum, nullable=False, server_default="Active"),
    )
    op.create_index("ix_consultation_sessions_clinic_id", "consultation_sessions", ["clinic_id"])
    op.create_index("ix_consultation_sessions_visit_id", "consultation_sessions", ["visit_id"])
    op.create_index("ix_consultation_sessions_doctor_id", "consultation_sessions", ["doctor_id"])
    op.create_index("ix_consultation_sessions_status", "consultation_sessions", ["status"])
    op.create_index("ix_consultation_sessions_legacy_id", "consultation_sessions", ["legacy_id"])
    op.create_index("ix_consultation_sessions_migration_batch_id", "consultation_sessions", ["migration_batch_id"])

    # --- visit_locks ---
    op.create_table(
        "visit_locks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("locked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("visit_id", "locked_at", name="uq_visit_lock_visit_locked_at"),
    )
    op.create_index("ix_visit_locks_clinic_id", "visit_locks", ["clinic_id"])
    op.create_index("ix_visit_locks_visit_id", "visit_locks", ["visit_id"])
    op.create_index("ix_visit_locks_locked_by", "visit_locks", ["locked_by"])
    op.create_index("ix_visit_locks_legacy_id", "visit_locks", ["legacy_id"])
    op.create_index("ix_visit_locks_migration_batch_id", "visit_locks", ["migration_batch_id"])

    # --- doctor_activity ---
    op.create_table(
        "doctor_activity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_meta", postgresql.JSONB(), nullable=True),
        sa.Column("legacy_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migration_batch_id", sa.String(length=64), nullable=True),
        sa.Column("migration_source", sa.String(length=100), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doctor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("visits.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type", doctor_activity_type_enum, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activity_metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_doctor_activity_clinic_id", "doctor_activity", ["clinic_id"])
    op.create_index("ix_doctor_activity_doctor_id", "doctor_activity", ["doctor_id"])
    op.create_index("ix_doctor_activity_user_id", "doctor_activity", ["user_id"])
    op.create_index("ix_doctor_activity_visit_id", "doctor_activity", ["visit_id"])
    op.create_index("ix_doctor_activity_activity_type", "doctor_activity", ["activity_type"])
    op.create_index("ix_doctor_activity_legacy_id", "doctor_activity", ["legacy_id"])
    op.create_index("ix_doctor_activity_migration_batch_id", "doctor_activity", ["migration_batch_id"])


def downgrade() -> None:
    op.drop_index("ix_doctor_activity_migration_batch_id", table_name="doctor_activity")
    op.drop_index("ix_doctor_activity_legacy_id", table_name="doctor_activity")
    op.drop_index("ix_doctor_activity_activity_type", table_name="doctor_activity")
    op.drop_index("ix_doctor_activity_visit_id", table_name="doctor_activity")
    op.drop_index("ix_doctor_activity_user_id", table_name="doctor_activity")
    op.drop_index("ix_doctor_activity_doctor_id", table_name="doctor_activity")
    op.drop_index("ix_doctor_activity_clinic_id", table_name="doctor_activity")
    op.drop_table("doctor_activity")

    op.drop_index("ix_visit_locks_migration_batch_id", table_name="visit_locks")
    op.drop_index("ix_visit_locks_legacy_id", table_name="visit_locks")
    op.drop_index("ix_visit_locks_locked_by", table_name="visit_locks")
    op.drop_index("ix_visit_locks_visit_id", table_name="visit_locks")
    op.drop_index("ix_visit_locks_clinic_id", table_name="visit_locks")
    op.drop_table("visit_locks")

    op.drop_index("ix_consultation_sessions_migration_batch_id", table_name="consultation_sessions")
    op.drop_index("ix_consultation_sessions_legacy_id", table_name="consultation_sessions")
    op.drop_index("ix_consultation_sessions_status", table_name="consultation_sessions")
    op.drop_index("ix_consultation_sessions_doctor_id", table_name="consultation_sessions")
    op.drop_index("ix_consultation_sessions_visit_id", table_name="consultation_sessions")
    op.drop_index("ix_consultation_sessions_clinic_id", table_name="consultation_sessions")
    op.drop_table("consultation_sessions")

    op.drop_index("ix_users_doctor_id", table_name="users")
    op.drop_column("users", "doctor_id")

    op.execute("DROP TYPE IF EXISTS doctor_activity_type")
    op.execute("DROP TYPE IF EXISTS consultation_session_status")
