"""ClinicService model - billable/consultable service catalog (master data only).

Named `ClinicService`/table `services` to avoid clashing with the `services/`
(business-logic layer) Python package. No billing logic lives here - this is
just the catalog consumed by future Billing/Queue/Appointments modules.
"""

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ClinicService(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "services"
    __table_args__ = (UniqueConstraint("clinic_id", "service_code", name="uq_service_clinic_code"),)

    service_code: Mapped[str] = mapped_column(String(30), nullable=False)
    service_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    duration_minutes: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active", server_default="Active")

    department: Mapped["Department | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClinicService id={self.id} service_name={self.service_name!r}>"


DEFAULT_SERVICES: list[dict] = [
    {"service_code": "CONS", "service_name": "Consultation", "default_price": 500, "duration_minutes": 20},
    {"service_code": "FOLLOWUP", "service_name": "Follow-up", "default_price": 300, "duration_minutes": 15},
    {"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": 200, "duration_minutes": 10},
    {"service_code": "LAB", "service_name": "Laboratory", "default_price": 400, "duration_minutes": 15},
    {"service_code": "DENTAL", "service_name": "Dental", "default_price": 800, "duration_minutes": 30},
    {"service_code": "VACC", "service_name": "Vaccination", "default_price": 350, "duration_minutes": 10},
    {"service_code": "MINSURG", "service_name": "Minor Surgery", "default_price": 2500, "duration_minutes": 45},
]
