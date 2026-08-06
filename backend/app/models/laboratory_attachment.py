"""Laboratory Attachments (Phase 10) - reuses the exact presigned-URL-stub
pattern from `consultation_attachments` (Phase 8), scoped to a
laboratory_order instead of a consultation. Kept as its own table (per
spec's explicit `LaboratoryAttachment` table listing) rather than
generalizing Phase 8's table, since consultation attachments and lab
attachments have different owning entities/lifecycles and parallel tables
keep both simple to reason about independently."""

import enum

import uuid

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LaboratoryAttachmentType(str, enum.Enum):
    PDF_REPORT = "PDFReport"
    IMAGE = "Image"
    SCANNED_RESULT = "ScannedResult"


class LaboratoryAttachment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_attachments"

    laboratory_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("laboratory_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attachment_type: Mapped[LaboratoryAttachmentType] = mapped_column(
        SAEnum(LaboratoryAttachmentType, name="laboratory_attachment_type", values_callable=_enum_values), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    laboratory_order: Mapped["LaboratoryOrder"] = relationship(back_populates="attachments")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryAttachment id={self.id} type={self.attachment_type!r}>"
