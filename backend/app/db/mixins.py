"""Reusable SQLAlchemy mixins: timestamps, soft-delete, multi-tenancy, legacy migration."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key generated both client-side and server-side."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """Adds created_at / updated_at columns with server-side defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds soft-delete flag and timestamp instead of hard row deletion."""

    is_deleted: Mapped[bool] = mapped_column(default=False, server_default=text("false"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantMixin:
    """Adds the clinic_id foreign key used to scope rows to a tenant (clinic)."""

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class LegacyMixin:
    """Tracks provenance for records migrated from the legacy Windows desktop app.

    `legacy_created_at`/`legacy_updated_at`/`migration_batch_id`/
    `migration_source`/`imported_at` were added in the Phase 5 migration
    (0005_reception_queue) as additive nullable columns so historical
    timestamps and batch/source provenance from a bulk import can be
    preserved without touching `created_at`/`updated_at` (which always
    reflect when the row was written to *this* database).
    """

    legacy_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    legacy_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    legacy_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legacy_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    migration_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    migration_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
