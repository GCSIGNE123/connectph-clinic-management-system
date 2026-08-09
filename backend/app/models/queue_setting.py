"""Queue configuration (pure configuration, no ticket/queue logic).

`QueueSetting` is a singleton-per-clinic (and optionally per-branch, via a
nullable branch_id + unique constraint) configuration row. `PriorityType` is
a small per-clinic reference list (Senior, PWD, Pregnant, Emergency, VIP...).
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class QueueSetting(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    __tablename__ = "queue_settings"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id", "branch_id", "department_id", "doctor_id",
            name="uq_queue_setting_clinic_branch_department_doctor",
        ),
    )

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Phase 5: nullable department scope. NULL = clinic/branch-wide default
    # prefix; a row with a department_id set overrides the default for that
    # department only (e.g. Dental queue tickets prefixed "D" instead of "A").
    # Kept as an added nullable column on the existing table (rather than a
    # new table) since it is still one prefix/config per (clinic, branch,
    # department) - the same shape as the existing config, just narrower.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): nullable
    # doctor scope, mirroring department_id above. NULL = the department (or
    # branch/clinic) default applies; a row with doctor_id set overrides the
    # prefix for that specific doctor only (e.g. Dr. A -> "A", Dr. B -> "B",
    # even when both sit in the same department). Resolution order lives in
    # `QueueSettingRepository.get_effective_for_doctor`: doctor override,
    # else department override, else branch/clinic default.
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=True, index=True
    )
    queue_prefix: Mapped[str] = mapped_column(String(10), nullable=False, default="A", server_default="A")
    max_daily_queue: Mapped[int] = mapped_column(Integer, nullable=False, default=200, server_default="200")
    reset_time: Mapped[str] = mapped_column(Time, nullable=False)
    allow_walkins: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_priority_lane: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    branch: Mapped["Branch | None"] = relationship()
    department: Mapped["Department | None"] = relationship()
    doctor: Mapped["Doctor | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QueueSetting id={self.id} prefix={self.queue_prefix!r}>"


class PriorityType(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    __tablename__ = "priority_types"
    __table_args__ = (UniqueConstraint("clinic_id", "code", name="uq_priority_type_clinic_code"),)

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PriorityType id={self.id} code={self.code!r}>"


DEFAULT_PRIORITY_TYPES: list[dict] = [
    {"code": "SENIOR", "label": "Senior Citizen"},
    {"code": "PWD", "label": "PWD"},
    {"code": "PREGNANT", "label": "Pregnant"},
    {"code": "EMERGENCY", "label": "Emergency"},
    {"code": "VIP", "label": "VIP"},
]
