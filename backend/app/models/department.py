"""Department model - clinical/organizational departments within a clinic."""

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Department(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A department/section of a clinic (e.g. Pediatrics, Dental, Laboratory)."""

    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("clinic_id", "department_code", name="uq_department_clinic_code"),)

    department_code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active", server_default="Active")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Department id={self.id} name={self.name!r}>"


DEFAULT_DEPARTMENTS: list[dict] = [
    {"department_code": "GEN", "name": "General Medicine", "color": "#2563eb"},
    {"department_code": "PED", "name": "Pediatrics", "color": "#f59e0b"},
    {"department_code": "OBG", "name": "OB-Gyne", "color": "#ec4899"},
    {"department_code": "IM", "name": "Internal Medicine", "color": "#0891b2"},
    {"department_code": "DEN", "name": "Dental", "color": "#16a34a"},
    {"department_code": "LAB", "name": "Laboratory", "color": "#7c3aed"},
    {"department_code": "RAD", "name": "Radiology", "color": "#64748b"},
    {"department_code": "PT", "name": "Physical Therapy", "color": "#dc2626"},
]
