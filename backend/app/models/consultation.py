"""Clinical Consultation (Phase 8).

`Consultation` sits on top of `Visit` exactly the way `Visit` sits on top of
`Queue` (see `models/visit.py`). One Consultation is opened per Visit (the
"Mark Consultation Complete" workflow step in the product spec ends the
clinical encounter) - see `services/consultation_service.py` for the design
decision on how `Consultation.status` reflects back onto `Visit.status`.

Design decision - one active Consultation per Visit: rather than a DB-level
unique constraint (which would make re-opening a *closed* consultation
impossible even for legitimate append-only history), the repository always
resolves "the" consultation for a visit via `ORDER BY created_at DESC LIMIT
1` ("latest wins"), and `open_consultation()` resumes the existing Draft/
InProgress row instead of creating a new one. This mirrors how
`VisitLock` keeps history rows instead of a hard unique-active constraint.

Design decision - reusing `visit_locks` for consultation locking: a Visit
and its Consultation are 1:1 (a consultation is just "the clinical detail of
this visit's encounter"), and Phase 7 already built `visit_locks` scoped to
`visit_id` with acquire/release/expiry/heartbeat semantics. Building a
second, parallel `consultation_locks` table would duplicate that logic for
no behavioural gain, so `ConsultationService` locking calls straight into
`DoctorWorkspaceRepository`'s existing lock methods keyed by `visit_id`.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class ConsultationStatus(str, enum.Enum):
    DRAFT = "Draft"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    SIGNED = "Signed"


# Legal forward transitions. Draft/InProgress are functionally interchangeable
# entry points (first meaningful SOAP save bumps Draft -> InProgress); only
# Completed -> Signed is a true one-way "lock-in" step.
CONSULTATION_STATUS_TRANSITIONS: dict[ConsultationStatus, set[ConsultationStatus]] = {
    ConsultationStatus.DRAFT: {ConsultationStatus.IN_PROGRESS, ConsultationStatus.COMPLETED},
    ConsultationStatus.IN_PROGRESS: {ConsultationStatus.COMPLETED},
    ConsultationStatus.COMPLETED: {ConsultationStatus.SIGNED},
    ConsultationStatus.SIGNED: set(),
}


class Consultation(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "consultations"

    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Denormalized for query convenience, consistent with how Visit
    # denormalizes patient_id rather than always joining through Visit.
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    status: Mapped[ConsultationStatus] = mapped_column(
        SAEnum(ConsultationStatus, name="consultation_status", values_callable=_enum_values),
        nullable=False,
        default=ConsultationStatus.DRAFT,
        server_default=ConsultationStatus.DRAFT.value,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    visit: Mapped["Visit"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    patient: Mapped["Patient"] = relationship()
    soap_note: Mapped["SoapNote | None"] = relationship(back_populates="consultation", uselist=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Consultation id={self.id} visit_id={self.visit_id} status={self.status!r}>"
