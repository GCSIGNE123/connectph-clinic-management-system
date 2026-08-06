"""Role model and the canonical RoleName enum used across the platform."""

import enum

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class RoleName(str, enum.Enum):
    """Canonical set of roles available within a clinic tenant."""

    OWNER = "Owner"
    ADMINISTRATOR = "Administrator"
    RECEPTIONIST = "Receptionist"
    DOCTOR = "Doctor"
    NURSE = "Nurse"
    CASHIER = "Cashier"
    LABORATORY = "Laboratory"
    PHARMACY = "Pharmacy"
    VIEWER = "Viewer"


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named role that can be assigned to users and granted permissions."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(back_populates="role")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Role id={self.id} name={self.name!r}>"
