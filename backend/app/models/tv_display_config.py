"""TV Display configuration (Phase 13) - Live TV Queue Display.

A `TvDisplayConfig` describes one physical/virtual display: its scope
(clinic-wide, or narrowed to a branch/department/doctor - "Waiting Area TV"
is simply a clinic-wide or branch-wide config with no department/doctor),
its visual settings (theme/font/queue size/animation/refresh interval/
logo/colors), and whether it is reachable without authentication via a
public slug URL (`is_public` + `public_slug`).

`tts_enabled`/`tts_template` are architecture-only per the Phase 13 spec -
`services/tts_service.py` renders the template into a real announcement
*string*; no audio synthesis is implemented.
"""

import enum
import secrets
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class TvDisplayTheme(str, enum.Enum):
    LIGHT = "Light"
    DARK = "Dark"
    CLINIC_BRANDED = "ClinicBranded"


class TvDisplayFontSize(str, enum.Enum):
    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    EXTRA_LARGE = "ExtraLarge"


class TvDisplayAnimationSpeed(str, enum.Enum):
    NONE = "None"
    SLOW = "Slow"
    NORMAL = "Normal"
    FAST = "Fast"


def _generate_public_slug() -> str:
    # URL-safe, unguessable token used as the public display's credential
    # (see services/tv_display_service.py for the security model).
    return secrets.token_urlsafe(24)


class TvDisplayConfig(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """One configured TV queue display.

    `branch_id`/`department_id`/`doctor_id` are all nullable, each narrowing
    the scope further (null = clinic-wide / not restricted at that level):
    clinic-wide -> branch-specific -> department-specific -> doctor-specific.
    A "Waiting Area TV" is just a branch-scoped config with no
    department/doctor set.
    """

    __tablename__ = "tv_display_configs"

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True, index=True
    )

    display_name: Mapped[str] = mapped_column(String(150), nullable=False)

    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    public_slug: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    # Post-RC1 (short TV display URL): optional, admin-chosen, short
    # human-typeable alias for the *same* public_slug row - e.g. "canora"
    # so a Smart TV remote can enter `/tv/canora` instead of the 32-char
    # `public_slug`. Deliberately NOT a replacement credential: it resolves
    # to the same TvDisplayConfig via the same is_public/is_active/
    # is_deleted filters as public_slug, and the response still carries the
    # real public_slug for the WebSocket handshake - see
    # `TvDisplayConfigRepository.get_by_short_code` and
    # `TvDisplayService.get_public_display_data`'s docstrings for the full
    # security-tradeoff rationale (short codes are inherently more
    # guessable than a 192-bit slug; mitigated by this being an explicit
    # admin opt-in, same posture as `is_public` itself, plus rate-limiting
    # on the public lookup endpoint). Unlike `public_slug`, never
    # auto-generated - blank/NULL means "no short alias configured", the
    # long `public_slug` URL keeps working unconditionally either way.
    short_code: Mapped[str | None] = mapped_column(String(32), nullable=True, unique=True, index=True)

    theme: Mapped[TvDisplayTheme] = mapped_column(
        SAEnum(TvDisplayTheme, name="tv_display_theme", values_callable=_enum_values),
        nullable=False, default=TvDisplayTheme.CLINIC_BRANDED, server_default=TvDisplayTheme.CLINIC_BRANDED.value,
    )
    font_size: Mapped[TvDisplayFontSize] = mapped_column(
        SAEnum(TvDisplayFontSize, name="tv_display_font_size", values_callable=_enum_values),
        nullable=False, default=TvDisplayFontSize.LARGE, server_default=TvDisplayFontSize.LARGE.value,
    )
    animation_speed: Mapped[TvDisplayAnimationSpeed] = mapped_column(
        SAEnum(TvDisplayAnimationSpeed, name="tv_display_animation_speed", values_callable=_enum_values),
        nullable=False, default=TvDisplayAnimationSpeed.NORMAL, server_default=TvDisplayAnimationSpeed.NORMAL.value,
    )
    queue_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10, server_default="10")
    refresh_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30, server_default="30")

    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)

    tts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    tts_template: Mapped[str | None] = mapped_column(
        Text, nullable=True, default="Queue {queue_number}, please proceed to {room}."
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    branch: Mapped["Branch | None"] = relationship()
    department: Mapped["Department | None"] = relationship()
    doctor: Mapped["Doctor | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TvDisplayConfig id={self.id} display_name={self.display_name!r}>"


def generate_public_slug() -> str:
    return _generate_public_slug()
