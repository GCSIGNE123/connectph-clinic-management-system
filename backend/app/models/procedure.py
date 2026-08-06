"""Procedure Orders (Phase 9).

Design decision: kept as its own lightweight table, NOT rows in `orders`,
per the spec listing "PROCEDURE ORDERS" as a standalone section with its
own field list (Procedure/Doctor/Date/Notes/Status - notably NO Order
Number, unlike the generic `orders` table). Folding it into `orders` would
mean either fabricating an order number nobody asked for or making that
column nullable just for this one category - a separate table matches the
spec literally and avoids that awkwardness. The Consultation's "Clinical
Orders" tab UI unifies both tables into one view for the doctor.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.order import OrderStatus


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Procedure(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "procedures"

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

    procedure_name: Mapped[str] = mapped_column(String(255), nullable=False)
    procedure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        SAEnum(OrderStatus, name="order_status", values_callable=_enum_values, create_type=False),
        nullable=False, default=OrderStatus.REQUESTED, server_default=OrderStatus.REQUESTED.value,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    consultation: Mapped["Consultation"] = relationship()
    doctor: Mapped["Doctor"] = relationship()
    patient: Mapped["Patient"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Procedure id={self.id} name={self.procedure_name!r} status={self.status!r}>"
