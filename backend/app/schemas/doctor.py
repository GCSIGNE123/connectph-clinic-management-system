"""Pydantic schemas for Doctor and DoctorSchedule resources."""

from datetime import datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.doctor import CONSULTATION_SECTION_IDS, SOAP_FIELD_IDS, DoctorStatus


class WorkspaceSectionConfig(BaseModel):
    visible: bool = True
    required: bool = False


class WorkspaceConfig(BaseModel):
    """Input shape for `DoctorUpdate.workspace_config` - validated against
    the current `CONSULTATION_SECTION_IDS`/`SOAP_FIELD_IDS` so a typo/unknown
    id is rejected up front (422) rather than silently ignored. The actual
    show/hide + required-only-if-visible resolution used everywhere else
    happens in `resolve_workspace_config`, not here."""

    sections: dict[str, WorkspaceSectionConfig] = Field(default_factory=dict)
    # Per-doctor SOAP note field visibility - {field_id: enabled}. See
    # `SOAP_FIELD_GROUPS` in `models/doctor.py` for the full field list and
    # why this is a flat bool map rather than a visible/required pair like
    # `sections` above.
    soap_fields: dict[str, bool] = Field(default_factory=dict)

    @field_validator("sections")
    @classmethod
    def _known_section_ids(
        cls, value: dict[str, WorkspaceSectionConfig]
    ) -> dict[str, WorkspaceSectionConfig]:
        unknown = set(value) - CONSULTATION_SECTION_IDS
        if unknown:
            raise ValueError(f"Unknown consultation section id(s): {', '.join(sorted(unknown))}")
        return value

    @field_validator("soap_fields")
    @classmethod
    def _known_soap_field_ids(cls, value: dict[str, bool]) -> dict[str, bool]:
        unknown = set(value) - SOAP_FIELD_IDS
        if unknown:
            raise ValueError(f"Unknown SOAP field id(s): {', '.join(sorted(unknown))}")
        return value


class DoctorBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    suffix: str | None = Field(default=None, max_length=20)
    prc_license: str | None = Field(default=None, max_length=50)
    ptr_number: str | None = Field(default=None, max_length=50)
    specialization: str | None = Field(default=None, max_length=150)
    department_id: UUID | None = None
    branch_id: UUID | None = None
    photo_url: str | None = Field(default=None, max_length=500)
    signature_url: str | None = Field(default=None, max_length=500)
    contact_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    consultation_fee: Decimal | None = None
    status: DoctorStatus = DoctorStatus.ACTIVE


class DoctorCreate(DoctorBase):
    # `signature_url` is deliberately NOT settable here (inherited from
    # `DoctorBase` but excluded below) - it must only ever be written by the
    # dedicated, validated `/doctors/{id}/signature` upload endpoint, never
    # as an arbitrary client-supplied string. See `DoctorService.upload_signature`.
    signature_url: None = Field(default=None, exclude=True)


class DoctorUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    suffix: str | None = Field(default=None, max_length=20)
    prc_license: str | None = Field(default=None, max_length=50)
    ptr_number: str | None = Field(default=None, max_length=50)
    specialization: str | None = Field(default=None, max_length=150)
    department_id: UUID | None = None
    branch_id: UUID | None = None
    photo_url: str | None = Field(default=None, max_length=500)
    # `signature_url` intentionally omitted - see `DoctorCreate` above.
    contact_number: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    consultation_fee: Decimal | None = None
    status: DoctorStatus | None = None
    workspace_config: WorkspaceConfig | None = None


class DoctorRead(DoctorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    doctor_code: str
    # Always the fully RESOLVED config (see `Doctor.effective_workspace_config`)
    # - a doctor with no custom configuration still returns every section
    # visible/not-required here, never null, so callers never have to
    # special-case "no config yet" themselves.
    workspace_config: dict = Field(validation_alias="effective_workspace_config")
    created_at: datetime
    updated_at: datetime


class DoctorSearchParams(BaseModel):
    q: str | None = None
    department_id: UUID | None = None
    branch_id: UUID | None = None
    status: DoctorStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DoctorListResponse(BaseModel):
    items: list[DoctorRead]
    total: int
    limit: int
    offset: int


class DoctorPhotoUploadResponse(BaseModel):
    upload_url: str
    public_url: str
    expires_in: int


# --- Doctor schedules ---


class DoctorScheduleBase(BaseModel):
    branch_id: UUID | None = None
    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: time
    end_time: time
    is_active: bool = True


class DoctorScheduleCreate(DoctorScheduleBase):
    pass


class DoctorScheduleUpdate(BaseModel):
    branch_id: UUID | None = None
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    is_active: bool | None = None


class DoctorScheduleRead(DoctorScheduleBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    doctor_id: UUID
    created_at: datetime
    updated_at: datetime
