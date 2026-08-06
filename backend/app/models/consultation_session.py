"""Consultation session tracking (Phase 7 - Doctor Workspace).

A `ConsultationSession` spans one "Start Consultation" -> "Complete
Consultation" doctor action for a given Visit. It exists alongside
`Visit.consultation_start` / `Visit.consultation_end` (which remain the
source of truth for the Visit's own timestamps) so that:

- multiple sessions could in principle exist per visit over time (e.g. a
  visit recalled from `NoShow` back to `Waiting` and consulted again), and
- `duration_seconds` gives the Doctor Dashboard a precomputed, queryable
  column for the "average consultation time" stat card rather than forcing
  every dashboard read to diff `Visit` timestamps across joined rows.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import (
    LegacyMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ConsultationSessionStatus(str, enum.Enum):
    ACTIVE = "Active"
    ENDED = "Ended"


class ConsultationSession(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "consultation_sessions"

    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ConsultationSessionStatus] = mapped_column(
        SAEnum(ConsultationSessionStatus, name="consultation_session_status", values_callable=_enum_values),
        nullable=False,
        default=ConsultationSessionStatus.ACTIVE,
        server_default=ConsultationSessionStatus.ACTIVE.value,
        index=True,
    )

    visit: Mapped["Visit"] = relationship()
    doctor: Mapped["Doctor"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConsultationSession id={self.id} visit_id={self.visit_id} status={self.status!r}>"
