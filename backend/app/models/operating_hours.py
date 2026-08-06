"""Weekly operating hours per clinic branch (Mon-Sun)."""

import uuid

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OperatingHours(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    __tablename__ = "operating_hours"
    __table_args__ = (
        UniqueConstraint("clinic_id", "branch_id", "day_of_week", name="uq_operating_hours_clinic_branch_day"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0=Monday .. 6=Sunday
    opening_time: Mapped[str | None] = mapped_column(Time, nullable=True)
    closing_time: Mapped[str | None] = mapped_column(Time, nullable=True)
    lunch_break_start: Mapped[str | None] = mapped_column(Time, nullable=True)
    lunch_break_end: Mapped[str | None] = mapped_column(Time, nullable=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    branch: Mapped["Branch"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OperatingHours id={self.id} branch_id={self.branch_id} day={self.day_of_week}>"
