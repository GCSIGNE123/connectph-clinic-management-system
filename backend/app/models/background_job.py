"""BackgroundJob model - architecture-level monitoring of real background tasks.

No real job-queue infrastructure exists in this project yet. Phase 14's
Legacy Migration Wizard imports are the one genuine example of a
long-running background-style task, and `MigrationService` writes a row here
alongside each `MigrationBatch` it creates. This table is NOT a fake/general
job system - it is a monitoring surface over what actually runs.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class BackgroundJobStatus(str, enum.Enum):
    SCHEDULED = "Scheduled"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
    RETRYING = "Retrying"


class BackgroundJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "background_jobs"

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[BackgroundJobStatus] = mapped_column(
        Enum(BackgroundJobStatus, name="background_job_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=BackgroundJobStatus.SCHEDULED,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    clinic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BackgroundJob id={self.id} job_type={self.job_type!r} status={self.status!r}>"
