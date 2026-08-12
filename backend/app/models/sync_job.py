"""SyncJob model - Post-RC1 Phase 2 Milestone 2: Cloud Backup (One-Way Sync).

Each row is one queued "upload this record to the cloud" unit of work,
created by `app/services/sync_queue_service.py::enqueue()` at the end of a
successful clinic-entity mutation (Patient, Visit, SOAP note, Queue ticket,
Prescription, Laboratory order/result, Payment, Shift). The background
`app/services/sync_worker_service.py` drains this table oldest-pending-first
against the cloud Backup API, applying exponential backoff on failure and
never discarding a job.

`payload` is a JSONB snapshot of the record at enqueue time (not a live
reference) - enough for the cloud endpoint to upsert it standalone, so the
worker never needs to re-read local state that may have since changed
further (a later mutation just enqueues a newer job with a fresher snapshot).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SyncJobStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncJobOperation(str, enum.Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class SyncJob(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "sync_jobs"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    operation: Mapped[SyncJobOperation] = mapped_column(
        String(20), nullable=False, default=SyncJobOperation.CREATE
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    status: Mapped[SyncJobStatus] = mapped_column(
        String(20), nullable=False, default=SyncJobStatus.PENDING, server_default=SyncJobStatus.PENDING.value, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SyncJob id={self.id} entity_type={self.entity_type!r} status={self.status!r}>"
