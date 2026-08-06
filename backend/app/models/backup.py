"""Backup model - real "trigger manual backup" record; restore is architecture-only (stub)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class BackupStatus(str, enum.Enum):
    PENDING = "Pending"
    COMPLETED = "Completed"
    FAILED = "Failed"


class Backup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "backups"

    backup_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    status: Mapped[BackupStatus] = mapped_column(
        Enum(BackupStatus, name="backup_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=BackupStatus.PENDING,
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admin_users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    storage_location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
