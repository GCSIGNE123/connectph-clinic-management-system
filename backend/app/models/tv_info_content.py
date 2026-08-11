"""TV Display Information/Advertisement Panel content (Post-RC1).

Deliberately a separate table from `tv_announcement.py`'s `TvAnnouncement`
(the existing bottom-of-screen scrolling ticker, unchanged/untouched by this
feature) rather than repurposing it: the two have materially different
shapes (this needs a title+body split, a `duration_seconds` rotation
interval, and a content-type taxonomy matching real clinic content
categories - pricing, doctor info, health tips, etc. - none of which map
cleanly onto `TvAnnouncement`'s single `message` field + Welcome/HealthTip/
Promotion/Emergency types) and different display mechanics (rotating,
one-at-a-time right-panel content vs. a continuously-scrolling ticker).
Clinic-wide only (no per-display scoping column) - simpler than
`TvAnnouncement`'s optional `tv_display_config_id`, since every TV Display
Post-RC1 renders the same 50/50 queue+info layout.
"""

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class TvInfoContentType(str, enum.Enum):
    SERVICE_PRICING = "ServicePricing"
    DOCTOR_INFO = "DoctorInfo"
    HEALTH_TIP = "HealthTip"
    PREVENTIVE_REMINDER = "PreventiveReminder"
    ANNOUNCEMENT = "Announcement"
    PROMOTION = "Promotion"
    MOTIVATIONAL = "Motivational"


DEFAULT_DURATION_SECONDS = 10


class TvInfoContent(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "tv_info_content"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[TvInfoContentType] = mapped_column(
        SAEnum(TvInfoContentType, name="tv_info_content_type", values_callable=_enum_values),
        nullable=False, default=TvInfoContentType.ANNOUNCEMENT, server_default=TvInfoContentType.ANNOUNCEMENT.value,
    )
    duration_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_DURATION_SECONDS, server_default=str(DEFAULT_DURATION_SECONDS)
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    # Prepared for future image support (spec item 7: "prepare the model/API
    # for future image support, but do not overbuild image upload unless
    # already supported by the architecture") - this codebase has no image
    # upload/storage service anywhere yet (logos/photos elsewhere are all
    # plain URL string fields too, e.g. `Clinic.logo_url`, `Doctor.photo_url`
    # - never a real upload pipeline), so this stays a nullable URL string,
    # consistent with that existing pattern, not a new upload feature.
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TvInfoContent id={self.id} title={self.title!r} type={self.content_type!r}>"
