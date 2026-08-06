"""Prescriptions (Phase 9). One "header" row (`Prescription`) per issuance,
with unlimited `PrescriptionItem` line items. Multiple prescriptions per
consultation are allowed (e.g. a corrected/reissued prescription) - callers
use "latest wins" query pattern consistent with how Consultation-per-Visit
was resolved in Phase 8 (see `ConsultationRepository.get_latest_for_visit`).

Allergy-conflict checking is architecture-only for this phase - see
`ClinicalOrdersService.check_allergy_conflicts()` docstring - there is no
drug/allergy database yet.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class PrescriptionStatus(str, enum.Enum):
    DRAFT = "Draft"
    FINALIZED = "Finalized"
    CANCELLED = "Cancelled"


class Prescription(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "prescriptions"

    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    prescription_number: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[PrescriptionStatus] = mapped_column(
        SAEnum(PrescriptionStatus, name="prescription_status", values_callable=_enum_values),
        nullable=False, default=PrescriptionStatus.DRAFT, server_default=PrescriptionStatus.DRAFT.value,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    consultation: Mapped["Consultation"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    patient: Mapped["Patient"] = relationship()
    items: Mapped[list["PrescriptionItem"]] = relationship(back_populates="prescription", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prescription id={self.id} number={self.prescription_number!r} status={self.status!r}>"


class PrescriptionItem(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "prescription_items"

    prescription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    medicine: Mapped[str] = mapped_column(String(255), nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dosage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    route: Mapped[str | None] = mapped_column(String(50), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    substitution_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    prescription: Mapped["Prescription"] = relationship(back_populates="items")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PrescriptionItem id={self.id} medicine={self.medicine!r}>"
