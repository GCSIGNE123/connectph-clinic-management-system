"""Consultation room model - physical rooms used for consultations per branch."""

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ConsultationRoom(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    __tablename__ = "consultation_rooms"

    room_name: Mapped[str] = mapped_column(String(150), nullable=False)
    room_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active", server_default="Active")

    department: Mapped["Department | None"] = relationship()
    branch: Mapped["Branch | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ConsultationRoom id={self.id} room_name={self.room_name!r}>"
