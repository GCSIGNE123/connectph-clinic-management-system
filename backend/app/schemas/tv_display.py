"""Pydantic schemas for TV Display configs, announcements, and the public
display payload."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.tv_announcement import TvAnnouncementType
from app.models.tv_display_config import TvDisplayAnimationSpeed, TvDisplayFontSize, TvDisplayTheme
from app.models.tv_info_content import DEFAULT_DURATION_SECONDS, TvInfoContentType


class TvDisplayConfigCreate(BaseModel):
    branch_id: UUID | None = None
    department_id: UUID | None = None
    doctor_id: UUID | None = None
    display_name: str = Field(min_length=1, max_length=150)
    is_public: bool = False
    theme: TvDisplayTheme = TvDisplayTheme.CLINIC_BRANDED
    font_size: TvDisplayFontSize = TvDisplayFontSize.LARGE
    animation_speed: TvDisplayAnimationSpeed = TvDisplayAnimationSpeed.NORMAL
    queue_size: int = Field(default=10, ge=1, le=50)
    refresh_interval_seconds: int = Field(default=30, ge=5, le=600)
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=20)
    secondary_color: str | None = Field(default=None, max_length=20)
    tts_enabled: bool = False
    tts_template: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class TvDisplayConfigUpdate(BaseModel):
    branch_id: UUID | None = None
    department_id: UUID | None = None
    doctor_id: UUID | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    is_public: bool | None = None
    theme: TvDisplayTheme | None = None
    font_size: TvDisplayFontSize | None = None
    animation_speed: TvDisplayAnimationSpeed | None = None
    queue_size: int | None = Field(default=None, ge=1, le=50)
    refresh_interval_seconds: int | None = Field(default=None, ge=5, le=600)
    logo_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=20)
    secondary_color: str | None = Field(default=None, max_length=20)
    tts_enabled: bool | None = None
    tts_template: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class TvDisplayConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    branch_id: UUID | None
    department_id: UUID | None
    doctor_id: UUID | None
    display_name: str
    is_public: bool
    public_slug: str | None
    theme: TvDisplayTheme
    font_size: TvDisplayFontSize
    animation_speed: TvDisplayAnimationSpeed
    queue_size: int
    refresh_interval_seconds: int
    logo_url: str | None
    primary_color: str | None
    secondary_color: str | None
    tts_enabled: bool
    tts_template: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class TvAnnouncementCreate(BaseModel):
    tv_display_config_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)
    announcement_type: TvAnnouncementType = TvAnnouncementType.WELCOME
    display_order: int = 0
    is_active: bool = True
    starts_at: date | None = None
    ends_at: date | None = None


class TvAnnouncementUpdate(BaseModel):
    message: str | None = Field(default=None, min_length=1, max_length=2000)
    announcement_type: TvAnnouncementType | None = None
    display_order: int | None = None
    is_active: bool | None = None
    starts_at: date | None = None
    ends_at: date | None = None


class TvAnnouncementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tv_display_config_id: UUID | None
    message: str
    announcement_type: TvAnnouncementType
    display_order: int
    is_active: bool
    starts_at: date | None
    ends_at: date | None
    created_at: datetime


class TvInfoContentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    content_type: TvInfoContentType = TvInfoContentType.ANNOUNCEMENT
    duration_seconds: int = Field(default=DEFAULT_DURATION_SECONDS, ge=3, le=120)
    display_order: int = 0
    is_active: bool = True
    image_url: str | None = Field(default=None, max_length=500)


class TvInfoContentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    content_type: TvInfoContentType | None = None
    duration_seconds: int | None = Field(default=None, ge=3, le=120)
    display_order: int | None = None
    is_active: bool | None = None
    image_url: str | None = Field(default=None, max_length=500)


class TvInfoContentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    body: str
    content_type: TvInfoContentType
    duration_seconds: int
    display_order: int
    is_active: bool
    image_url: str | None
    created_at: datetime
    updated_at: datetime


class TvDisplayNowServing(BaseModel):
    queue_id: UUID
    queue_number: str
    patient_initials: str
    doctor_name: str | None
    # Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): department
    # context, additive alongside the existing doctor_name. Lets the
    # frontend group/label a mixed multi-department/multi-doctor result set
    # by destination - doctor name when assigned, else department name
    # (e.g. a Laboratory/Radiology department-only ticket with no doctor).
    department_id: UUID | None = None
    department_name: str | None = None
    room_name: str | None
    status: str
    called_at: datetime | None


class TvDisplayWaitingEntry(BaseModel):
    queue_id: UUID
    queue_number: str
    patient_initials: str
    doctor_name: str | None
    department_id: UUID | None = None
    department_name: str | None = None
    priority: str


class TvDisplayData(BaseModel):
    """Shape returned by both the public and the authenticated-preview
    display-data endpoints - identical payload either way."""

    display_name: str
    clinic_name: str
    branch_name: str | None
    theme: TvDisplayTheme
    font_size: TvDisplayFontSize
    animation_speed: TvDisplayAnimationSpeed
    queue_size: int
    refresh_interval_seconds: int
    logo_url: str | None
    primary_color: str | None
    secondary_color: str | None
    now_serving: list[TvDisplayNowServing]
    next_waiting: list[TvDisplayWaitingEntry]
    announcements: list[TvAnnouncementRead]
    info_content: list[TvInfoContentRead]
    server_time: datetime
    ws_channel_clinic_id: UUID
    ws_auth_slug: str | None
