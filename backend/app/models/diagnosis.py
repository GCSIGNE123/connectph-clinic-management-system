"""Diagnosis (Phase 8). ICD-10 fields are architecture-only (plain optional
text, no search/autocomplete UI per spec)."""

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class DiagnosisType(str, enum.Enum):
    PRIMARY = "Primary"
    SECONDARY = "Secondary"


class DiagnosisStatus(str, enum.Enum):
    WORKING = "Working"
    FINAL = "Final"


class Diagnosis(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "diagnoses"

    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    diagnosis_type: Mapped[DiagnosisType] = mapped_column(
        SAEnum(DiagnosisType, name="diagnosis_type", values_callable=_enum_values), nullable=False
    )
    status: Mapped[DiagnosisStatus] = mapped_column(
        SAEnum(DiagnosisStatus, name="diagnosis_status", values_callable=_enum_values),
        nullable=False,
        default=DiagnosisStatus.WORKING,
        server_default=DiagnosisStatus.WORKING.value,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    icd10_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    icd10_description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Phase 18 (Patient Portal): explicit opt-in flag. Clinic staff must
    # deliberately mark a diagnosis patient-visible; the safer default is
    # False so nothing is exposed to the Patient Portal's Medical Records
    # view unless a clinician has reviewed and approved it for sharing.
    patient_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    consultation: Mapped["Consultation"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Diagnosis id={self.id} type={self.diagnosis_type!r} status={self.status!r}>"
