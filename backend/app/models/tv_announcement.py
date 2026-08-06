"""TV display announcements (Phase 13) - scrolling ticker content shown at
the bottom of a Live TV Queue Display."""

import enum
import uuid
from datetime import date as date_type

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class TvAnnouncementType(str, enum.Enum):
    WELCOME = "Welcome"
    HEALTH_TIP = "HealthTip"
    PROMOTION = "Promotion"
    EMERGENCY = "Emergency"


class TvAnnouncement(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "tv_announcements"

    tv_display_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tv_display_configs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    message: Mapped[str] = mapped_column(Text, nullable=False)
    announcement_type: Mapped[TvAnnouncementType] = mapped_column(
        SAEnum(TvAnnouncementType, name="tv_announcement_type", values_callable=_enum_values),
        nullable=False, default=TvAnnouncementType.WELCOME, server_default=TvAnnouncementType.WELCOME.value,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    starts_at: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    tv_display_config: Mapped["TvDisplayConfig | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TvAnnouncement id={self.id} type={self.announcement_type!r}>"
