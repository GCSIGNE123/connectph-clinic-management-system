"""Consultation attachments (Phase 8) - real upload path for Clinical
Images / PDFs / Referral Letters. Lab Requests stay a placeholder with no
upload path (no `LAB_REQUEST` member here by design - see product spec).

Uses the same presigned-URL-stub pattern as
`PatientService.request_photo_upload_url` (no Supabase project provisioned
yet in dev - see that method's TODO for the real integration)."""

import enum
import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class AttachmentType(str, enum.Enum):
    CLINICAL_IMAGE = "ClinicalImage"
    PDF = "PDF"
    REFERRAL_LETTER = "ReferralLetter"


class ConsultationAttachment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "consultation_attachments"

    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("consultations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attachment_type: Mapped[AttachmentType] = mapped_column(
        SAEnum(AttachmentType, name="consultation_attachment_type", values_callable=_enum_values), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Phase 18 (Patient Portal): same explicit opt-in rationale as
    # `Diagnosis.patient_visible` - default False, clinic staff must mark an
    # attachment visible before a patient can see/download it in the portal.
    patient_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    consultation: Mapped["Consultation"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConsultationAttachment id={self.id} type={self.attachment_type!r}>"
