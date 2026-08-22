"""User model - a clinic staff member / platform account."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import (
    LegacyMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class UserStatus(str, enum.Enum):
    """Coarse-grained account status, distinct from soft-delete."""

    ACTIVE = "active"
    DISABLED = "disabled"
    LOCKED = "locked"


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A staff account belonging to a clinic tenant, with a single assigned role."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    mobile_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    profile_photo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Laboratory Report signatories (Round 6): a Laboratory-role user's own
    # professional license/registration number and e-signature, meaningful
    # only for that role (same "nullable, only meaningful for one role"
    # convention as `doctor_id` above). Reused generically on `User` rather
    # than a separate "Med Tech" entity - the Med Tech in Charge IS the
    # authenticated Laboratory user, so their signature belongs on their own
    # account, self-managed like the rest of this profile.
    license_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Phase 7 (Doctor Workspace): nullable link resolving "which Doctor
    # record does this logged-in User correspond to", so a User with the
    # Doctor role can be scoped to "their own" assigned Visits. Only
    # meaningful for Doctor-role users; left NULL for everyone else. Added
    # as a simple FK (rather than a link table) since the relationship is
    # 1:1 in practice - a login belongs to exactly one Doctor record.
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    clinic: Mapped["Clinic"] = relationship(back_populates="users")
    role: Mapped["Role"] = relationship(back_populates="users")
    branch: Mapped["Branch | None"] = relationship(foreign_keys=[branch_id])
    doctor: Mapped["Doctor | None"] = relationship(foreign_keys=[doctor_id])

    __table_args__ = (
        UniqueConstraint("clinic_id", "email", name="uq_user_clinic_email"),
        UniqueConstraint("clinic_id", "username", name="uq_user_clinic_username"),
    )

    @property
    def role_name(self) -> str | None:
        """Convenience accessor used by `UserRead` serialization.

        Only safe to access when `role` was eager-loaded (e.g. via
        `selectinload(User.role)` in the repository query) - all current
        call sites that serialize `UserRead` do this.
        """
        return self.role.name if self.role is not None else None

    @property
    def full_name(self) -> str:
        if self.middle_name:
            return f"{self.first_name} {self.middle_name} {self.last_name}"
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r}>"
