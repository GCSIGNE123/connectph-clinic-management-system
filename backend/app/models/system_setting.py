"""SystemSetting model - per-clinic key/value configuration store."""

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SystemSetting(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    """A single configuration key/value pair scoped to a clinic tenant."""

    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("clinic_id", "key", name="uq_system_setting_clinic_key"),)

    key: Mapped[str] = mapped_column(String(150), nullable=False)
    value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SystemSetting id={self.id} key={self.key!r}>"
