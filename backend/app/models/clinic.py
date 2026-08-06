"""Clinic model - the top-level tenant entity.

Phase 4 extends this with clinic-settings fields (address breakdown, legal
identifiers, locale/format preferences) and branding fields. This remains a
single row per tenant - there is no separate "clinic settings" table; the
clinic row IS the settings record (see docs/DATABASE.md).
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Clinic(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, LegacyMixin, Base):
    """A single tenant of the platform: one physical/legal clinic organization."""

    __tablename__ = "clinics"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Phase 4: clinic settings (singleton-per-clinic) ---
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    barangay: Mapped[str | None] = mapped_column(String(150), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telephone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mobile: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    license_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Manila", server_default="Asia/Manila")
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en", server_default="en")
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="PHP", server_default="PHP")
    date_format: Mapped[str] = mapped_column(String(20), nullable=False, default="MM/DD/YYYY", server_default="MM/DD/YYYY")
    time_format: Mapped[str] = mapped_column(String(10), nullable=False, default="12h", server_default="12h")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Active", server_default="Active")

    # --- Phase 15: SaaS Administration (platform-level tenant lifecycle) ---
    # `status` (above) is reused/extended to also carry "Suspended"/"Archived"
    # values (it was already Active/... from Phase 4's clinic-settings work).
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Phase 4: branding (kept on the clinic row - see module 10 design note) ---
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    login_background_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    theme: Mapped[str] = mapped_column(String(20), nullable=False, default="system", server_default="system")

    # Phase 21 (Vitals-before-Queue): per-clinic toggle for whether Head
    # Circumference is a required vitals field (it's optional everywhere by
    # default - Pain Score is always optional, unconditionally, per spec).
    # A minimal boolean rather than a richer "which vitals are required"
    # config table since Height/Weight/BP/Temp/Pulse/RR/SpO2 are always
    # required and nothing else in the spec needs to be configurable.
    require_head_circumference: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    branches: Mapped[list["Branch"]] = relationship(
        back_populates="clinic", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(back_populates="clinic", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="clinic", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Clinic id={self.id} slug={self.slug!r}>"
