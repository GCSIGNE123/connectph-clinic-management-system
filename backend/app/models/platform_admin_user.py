"""PlatformAdminUser model - a CONNECT.PH staff account, structurally separate from tenant `users`.

Phase 15 design decision (option "b" from the phase spec): platform
administrators are NOT rows in the tenant-scoped `users` table. They do not
belong to any clinic (`clinic_id` never applies to them), and their JWTs use a
completely different claim shape (`app.core.platform_admin_security`) so a
platform-admin token can never be misinterpreted by the existing
`get_current_user`/`get_current_clinic_id` dependency chain, and vice-versa.
See docs/ARCHITECTURE.md "Two-Portal Architecture" for the full rationale.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PlatformAdminRole(str, enum.Enum):
    PLATFORM_ADMINISTRATOR = "PlatformAdministrator"
    SUPPORT_ENGINEER = "SupportEngineer"
    IMPLEMENTATION_TEAM = "ImplementationTeam"
    AUDITOR = "Auditor"


class PlatformAdminUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A CONNECT.PH platform staff account. Deliberately has no `clinic_id`."""

    __tablename__ = "platform_admin_users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[PlatformAdminRole] = mapped_column(
        Enum(PlatformAdminRole, name="platform_admin_role", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=PlatformAdminRole.SUPPORT_ENGINEER,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PlatformAdminUser id={self.id} email={self.email!r} role={self.role!r}>"


# Roles permitted to WRITE (create/edit/suspend/etc.) vs. read-only.
# Auditor is intentionally read-only across the whole platform-admin surface.
PLATFORM_ADMIN_WRITE_ROLES = {
    PlatformAdminRole.PLATFORM_ADMINISTRATOR,
    PlatformAdminRole.SUPPORT_ENGINEER,
    PlatformAdminRole.IMPLEMENTATION_TEAM,
}
PLATFORM_ADMIN_FULL_ROLES = {PlatformAdminRole.PLATFORM_ADMINISTRATOR}
