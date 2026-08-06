"""Pydantic schemas for clinic (tenant) resources."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ClinicBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)


class ClinicCreate(ClinicBase):
    slug: str = Field(min_length=1, max_length=100)


class ClinicUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class ClinicRead(ClinicBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --- Phase 4: clinic settings (singleton-per-clinic) + branding ---


class ClinicSettingsRead(BaseModel):
    """GET /clinic-settings - the full settings + branding view of the clinic row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    short_name: str | None = None
    address: str | None = None
    province: str | None = None
    city: str | None = None
    barangay: str | None = None
    zip_code: str | None = None
    telephone: str | None = None
    mobile: str | None = None
    email: EmailStr | None = None
    website: str | None = None
    tin: str | None = None
    license_number: str | None = None
    logo_url: str | None = None
    timezone: str
    language: str
    currency: str
    date_format: str
    time_format: str
    status: str
    # Branding
    favicon_url: str | None = None
    login_background_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    theme: str
    # Phase 21 (Vitals-before-Queue): whether Head Circumference is a
    # required vitals field for this clinic (always optional elsewhere -
    # see `services/queue_service.py::REQUIRED_VITALS_FIELDS`).
    require_head_circumference: bool = False
    created_at: datetime
    updated_at: datetime


class ClinicSettingsUpdate(BaseModel):
    """PUT /clinic-settings - all fields optional (partial update)."""

    name: str | None = Field(default=None, max_length=255)
    short_name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=500)
    province: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=150)
    barangay: str | None = Field(default=None, max_length=150)
    zip_code: str | None = Field(default=None, max_length=20)
    telephone: str | None = Field(default=None, max_length=50)
    mobile: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    website: str | None = Field(default=None, max_length=255)
    tin: str | None = Field(default=None, max_length=50)
    license_number: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=10)
    currency: str | None = Field(default=None, max_length=10)
    date_format: str | None = Field(default=None, max_length=20)
    time_format: str | None = Field(default=None, max_length=10)
    status: str | None = Field(default=None, max_length=20)
    require_head_circumference: bool | None = None


class ClinicBrandingUpdate(BaseModel):
    """PATCH /clinic-settings/branding - branding-only partial update."""

    logo_url: str | None = Field(default=None, max_length=500)
    favicon_url: str | None = Field(default=None, max_length=500)
    login_background_url: str | None = Field(default=None, max_length=500)
    primary_color: str | None = Field(default=None, max_length=20)
    secondary_color: str | None = Field(default=None, max_length=20)
    theme: str | None = Field(default=None, max_length=20, pattern="^(light|dark|system)$")


class BrandingUploadResponse(BaseModel):
    """Presigned-URL stub for logo/favicon/login-background uploads."""

    upload_url: str
    public_url: str
    expires_in: int
