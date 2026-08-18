"""Referrals (Phase 9). Kept as its own table (not an `orders` row with
category=Referral) since the spec's DATABASE section explicitly lists
"Referral" as a top-level table name alongside Orders/Procedures - matching
that literally, and it has its own `referred_to`/`reason` fields distinct
from the generic order shape."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.order import OrderStatus


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Referral(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "referrals"

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

    referred_to: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", values_callable=_enum_values, create_type=False),
        nullable=False, default=OrderStatus.REQUESTED, server_default=OrderStatus.REQUESTED.value,
    )

    # Doctor E-Signature: snapshot of `Doctor.signature_url` copied in at
    # creation time (no separate "finalize" step for a Referral - creation
    # IS issuance), NOT a live join - see migration 0036's docstring.
    doctor_signature_snapshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    consultation: Mapped["Consultation"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    patient: Mapped["Patient"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Referral id={self.id} referred_to={self.referred_to!r} status={self.status!r}>"
