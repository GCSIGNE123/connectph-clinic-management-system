"""SyncedRecord model - Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync).

This is the table a CLOUD-hosted instance of this codebase (pointed at
`CLOUD_DATABASE_URL` instead of a clinic's local database) stores incoming
backup uploads into, via `POST /api/v1/backup/{entity_type}`
(`app/api/v1/backup.py`). It intentionally is NOT the same relational shape
as the source tables (`patients`, `visits`, ...): replaying a JSONB snapshot
into fully-normalized cloud-side `patients`/`visits`/... tables would require
the cloud database to also independently mirror every foreign-keyed parent
row (clinics, users, doctors, ...) in dependency order, which is out of
scope for a one-way *backup* (whose job is "have an off-site, restorable
copy of the data", not "run a live relational replica"). Instead each
upload is stored as one upsert-by-`(clinic_id, entity_type, record_id)` row
holding the full payload snapshot - simple, dependency-free, and sufficient
to restore/inspect data if a clinic's local database is ever lost.

Deliberately has NO foreign key to `clinics.id`: the whole point of this
table is that it can receive uploads for a clinic whose `Clinic` row may not
independently exist in this cloud database (Clinic/User sync is out of
scope for this milestone, see `docs/FEATURES.md`).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SyncedRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "synced_records"

    clinic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("clinic_id", "entity_type", "record_id", name="uq_synced_records_clinic_entity_record"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SyncedRecord entity_type={self.entity_type!r} record_id={self.record_id}>"
