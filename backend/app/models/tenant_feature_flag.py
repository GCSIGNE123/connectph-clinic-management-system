"""TenantFeatureFlag model - per-clinic module toggles managed by platform admins."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# The set of known feature keys. Only "appointments" is actually wired into a
# real nav-visibility check (proof of concept, see feature_flag_service.py);
# the rest exist as togglable placeholders per the phase spec.
KNOWN_FEATURE_KEYS = (
    "appointments",
    "laboratory",
    "tv_queue",
    "migration_wizard",
    "inventory",
    "teleconsultation",
    "ai_assistant",
    "patient_portal",
)


class TenantFeatureFlag(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_feature_flags"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("platform_admin_users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (UniqueConstraint("clinic_id", "feature_key", name="uq_tenant_feature_flag"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TenantFeatureFlag clinic_id={self.clinic_id} feature_key={self.feature_key!r} enabled={self.is_enabled}>"
