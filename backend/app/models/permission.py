"""Permission model - a pure lookup table of grantable permission codes."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class Permission(UUIDPrimaryKeyMixin, Base):
    """A single grantable permission, e.g. `patients:read`, `billing:write`.

    Pure lookup table: no timestamps/soft-delete, matching spec guidance for
    tables like this.
    """

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Permission id={self.id} code={self.code!r}>"
