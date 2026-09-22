"""A Doctor's personal saved ("My Phrases") suggestion phrase for one SOAP / diagnosis field.

Task #2 enhancement. A row belongs to exactly one clinic + Doctor + field, so a
phrase saved for `chief_complaint` is never offered for `treatment_plan`, and
one Doctor's phrases are never visible to another Doctor. It is a personal
preference, not clinical data: it holds only the short phrase text (never a
patient/consultation reference), and un-favoriting hard-deletes the row.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

PHRASE_MAX_LENGTH = 80


class SoapPhraseFavorite(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "soap_phrase_favorites"
    __table_args__ = (
        UniqueConstraint("clinic_id", "doctor_id", "field", "phrase_key", name="uq_soap_phrase_favorite"),
        Index("ix_soap_phrase_favorites_clinic_doctor_field", "clinic_id", "doctor_id", "field"),
    )

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    # Display form as the Doctor typed it (whitespace-normalized); `phrase_key` is its lower-cased twin,
    # used for the uniqueness / case-insensitive duplicate check.
    phrase: Mapped[str] = mapped_column(String(PHRASE_MAX_LENGTH), nullable=False)
    phrase_key: Mapped[str] = mapped_column(String(PHRASE_MAX_LENGTH), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SoapPhraseFavorite id={self.id} field={self.field!r}>"
