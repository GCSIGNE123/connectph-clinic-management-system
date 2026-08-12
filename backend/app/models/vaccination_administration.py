"""Vaccination Administration (Post-RC1): the vaccination department's own
workflow record layered 1:1 on top of a Phase 9 `Order`
(order_category=Vaccination), mirroring `models/laboratory_order.py`'s
"separate table on top of orders" design.

Status machine is deliberately simple - Requested -> Administered, or ->
Cancelled from Requested - unlike Laboratory's five-state machine, there is
no processing/results step: a vaccination either has been given or it
hasn't. Who may transition Requested -> Administered is intentionally
broader than other order categories (see `VACCINATION_ADMINISTER_ROLES` in
`core/dependencies.py`): any Nurse or Receptionist may administer, not just
the ordering doctor, matching real clinic staffing.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class VaccinationStatus(str, enum.Enum):
    REQUESTED = "Requested"
    ADMINISTERED = "Administered"
    CANCELLED = "Cancelled"


VACCINATION_STATUS_TRANSITIONS: dict[VaccinationStatus, set[VaccinationStatus]] = {
    VaccinationStatus.REQUESTED: {VaccinationStatus.ADMINISTERED, VaccinationStatus.CANCELLED},
    VaccinationStatus.ADMINISTERED: set(),
    VaccinationStatus.CANCELLED: set(),
}


class VaccinationAdministration(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "vaccination_administrations"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True)
    visit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True)

    # What the doctor ordered (copied from the order's first item at
    # creation time, same "best-effort convenience copy" as Laboratory's
    # `test_type`) - editable at administration time in case the actual
    # vaccine given differs (e.g. brand substitution).
    vaccine_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[VaccinationStatus] = mapped_column(
        SAEnum(VaccinationStatus, name="vaccination_status", values_callable=_enum_values),
        nullable=False, default=VaccinationStatus.REQUESTED, server_default=VaccinationStatus.REQUESTED.value,
    )

    # Populated only at administration time.
    dose: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lot_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    site: Mapped[str | None] = mapped_column(String(100), nullable=True)
    route: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    administered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    administered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    order: Mapped["Order"] = relationship()
    patient: Mapped["Patient"] = relationship()
    doctor: Mapped["Doctor"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VaccinationAdministration id={self.id} vaccine_name={self.vaccine_name!r} status={self.status!r}>"
