"""Doctor-specific activity log (Phase 7 - Doctor Workspace).

Mirrors the relationship `visit_timeline_events` has to `audit_logs`
(Phase 6): this table is a domain-specific, fast-to-query log scoped to
doctor actions, feeding the Doctor Dashboard's stat cards, while every
action *also* writes a generic `audit_logs` entry via `AuditService` for
the cross-cutting security/compliance trail. Keeping them separate avoids
making dashboard queries scan/filter the much larger generic audit table.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class DoctorActivityType(str, enum.Enum):
    PATIENT_CALLED = "PatientCalled"
    PATIENT_RECALLED = "PatientRecalled"
    CONSULTATION_STARTED = "ConsultationStarted"
    CONSULTATION_COMPLETED = "ConsultationCompleted"
    MARKED_NO_SHOW = "MarkedNoShow"
    VISIT_CANCELLED = "VisitCancelled"
    VISIT_OPENED = "VisitOpened"


class DoctorActivity(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "doctor_activity"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="SET NULL"), nullable=True, index=True
    )
    activity_type: Mapped[DoctorActivityType] = mapped_column(
        SAEnum(DoctorActivityType, name="doctor_activity_type", values_callable=_enum_values),
        nullable=False,
        index=True,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activity_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    doctor: Mapped["Doctor"] = relationship()
    user: Mapped["User"] = relationship()
    visit: Mapped["Visit | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DoctorActivity id={self.id} type={self.activity_type!r}>"
