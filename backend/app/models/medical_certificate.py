"""Medical Certificates.

Kept as its own standalone table (not an `orders` row), following the exact
same precedent `Referral`/`Prescription` already set - a certificate is a
legally-relevant document with its own lifecycle, not a generic clinical
order.

Lifecycle: `Draft -> Issued -> Cancelled`. A Draft is a working copy the
issuing doctor may freely edit - it is NOT a legal document yet. Once
`Issued`, the row becomes immutable (no field on it may be mutated by any
API - see `MedicalCertificateService`); correcting an issued certificate
means Cancelling it (with a required reason) and creating a brand-new row
with a new `certificate_number`, linked back via `superseded_by_id` so the
cancelled original stays visible in history/audit rather than disappearing.

Deliberately NOT stored on this row (pulled live at read/print time instead,
mirroring how Prescription's print template already pulls doctor PRC/PTR
and clinic branding live rather than storing them):
- patient name/age/sex (from `Patient` via `patient_id`)
- doctor name/PRC license/PTR number (from `Doctor` via `doctor_id`)
- clinic name/logo/address (from `Clinic` via the request's `clinic_id`)
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class MedicalCertificateType(str, enum.Enum):
    MEDICAL_CERTIFICATE = "MedicalCertificate"
    FIT_TO_WORK = "FitToWork"
    SICK_LEAVE = "SickLeave"
    CUSTOM = "Custom"


class MedicalCertificateStatus(str, enum.Enum):
    DRAFT = "Draft"
    ISSUED = "Issued"
    CANCELLED = "Cancelled"


class MedicalCertificate(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "medical_certificates"

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
    # NOT NULL, unlike Referral/Prescription's nullable doctor_id - a
    # certificate always has one issuing doctor (product decision: the
    # consultation's assigned doctor).
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    certificate_number: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    certificate_type: Mapped[MedicalCertificateType] = mapped_column(
        SAEnum(MedicalCertificateType, name="medical_certificate_type", values_callable=_enum_values),
        nullable=False,
    )
    status: Mapped[MedicalCertificateStatus] = mapped_column(
        SAEnum(MedicalCertificateStatus, name="medical_certificate_status", values_callable=_enum_values),
        nullable=False, default=MedicalCertificateStatus.DRAFT, server_default=MedicalCertificateStatus.DRAFT.value,
    )

    findings: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    rest_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Self-reference: set on the OLD (cancelled) row, pointing at the NEW
    # certificate that replaced it - so the cancelled original stays
    # visible in history/audit with a clear "superseded by MC-..." link,
    # rather than being an orphaned dead end. Nullable (most certificates
    # are never superseded); SET NULL on delete of the replacement so a
    # (soft-)deleted successor never leaves a dangling FK.
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medical_certificates.id", ondelete="SET NULL"), nullable=True
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Doctor E-Signature: snapshot of `Doctor.signature_url` copied in at
    # `issue()` time (a Draft has none - it's not a legal document yet),
    # NOT a live join like the doctor name/PRC/PTR fields above - a
    # deliberate, scoped exception (see migration 0036's docstring): the
    # signature represents what was actually applied to THIS certificate
    # at issue time. Replacing/removing the doctor's current signature
    # afterward must never change what an already-issued certificate prints.
    doctor_signature_snapshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    consultation: Mapped["Consultation"] = relationship()
    doctor: Mapped["Doctor"] = relationship(foreign_keys=[doctor_id])
    patient: Mapped["Patient"] = relationship()
    superseded_by: Mapped["MedicalCertificate | None"] = relationship(remote_side="MedicalCertificate.id")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MedicalCertificate id={self.id} number={self.certificate_number!r} status={self.status!r}>"
