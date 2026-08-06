"""Pydantic schemas for patient resources."""

import re
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.patient import BloodType, CivilStatus, Gender, PatientStatus

MOBILE_NUMBER_PATTERN = re.compile(r"^\+?[0-9]{7,15}$")


def _validate_mobile_number(value: str) -> str:
    if not MOBILE_NUMBER_PATTERN.match(value):
        raise ValueError("Mobile number must be 7-15 digits, optionally prefixed with '+'.")
    return value


def _validate_optional_mobile_number(value: str | None) -> str | None:
    if value is None:
        return value
    return _validate_mobile_number(value)


class PatientBase(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    suffix: str | None = Field(default=None, max_length=20)

    birth_date: date
    gender: Gender
    civil_status: CivilStatus
    nationality: str = Field(default="Filipino", max_length=100)

    address_line: str | None = Field(default=None, max_length=255)
    barangay: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=150)
    province: str | None = Field(default=None, max_length=150)
    zip_code: str | None = Field(default=None, max_length=20)

    mobile_number: str = Field(max_length=20)
    telephone_number: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None

    occupation: str | None = Field(default=None, max_length=150)
    employer: str | None = Field(default=None, max_length=150)

    blood_type: BloodType | None = None
    allergies: str | None = None
    medical_notes: str | None = None
    remarks: str | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=20)

    branch_id: UUID | None = None

    @field_validator("mobile_number")
    @classmethod
    def _check_mobile_number(cls, value: str) -> str:
        return _validate_mobile_number(value)

    @field_validator("birth_date")
    @classmethod
    def _check_birth_date_not_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Birth date cannot be in the future.")
        return value


class PatientCreate(PatientBase):
    legacy_patient_id: str | None = Field(default=None, max_length=64)
    photo_url: str | None = Field(default=None, max_length=500)


class PatientUpdate(BaseModel):
    """Partial update payload - all fields optional, only supplied fields are applied."""

    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    suffix: str | None = Field(default=None, max_length=20)

    birth_date: date | None = None
    gender: Gender | None = None
    civil_status: CivilStatus | None = None
    nationality: str | None = Field(default=None, max_length=100)

    address_line: str | None = Field(default=None, max_length=255)
    barangay: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=150)
    province: str | None = Field(default=None, max_length=150)
    zip_code: str | None = Field(default=None, max_length=20)

    mobile_number: str | None = Field(default=None, max_length=20)
    telephone_number: str | None = Field(default=None, max_length=20)
    email: EmailStr | None = None

    occupation: str | None = Field(default=None, max_length=150)
    employer: str | None = Field(default=None, max_length=150)

    blood_type: BloodType | None = None
    allergies: str | None = None
    medical_notes: str | None = None
    remarks: str | None = None
    emergency_contact_name: str | None = Field(default=None, max_length=150)
    emergency_contact_phone: str | None = Field(default=None, max_length=20)

    photo_url: str | None = Field(default=None, max_length=500)
    branch_id: UUID | None = None

    @field_validator("mobile_number")
    @classmethod
    def _check_mobile_number(cls, value: str | None) -> str | None:
        return _validate_optional_mobile_number(value)

    @field_validator("birth_date")
    @classmethod
    def _check_birth_date_not_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Birth date cannot be in the future.")
        return value


class PatientRead(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    patient_number: str
    legacy_patient_id: str | None = None
    photo_url: str | None = None
    qr_code: str | None = None
    status: PatientStatus
    date_registered: date
    last_visit: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PatientListItem(BaseModel):
    """Slim projection used for table rows - avoids shipping medical notes etc."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_number: str
    first_name: str
    middle_name: str | None = None
    last_name: str
    suffix: str | None = None
    birth_date: date
    gender: Gender
    mobile_number: str
    photo_url: str | None = None
    branch_id: UUID | None = None
    status: PatientStatus
    date_registered: date
    last_visit: datetime | None = None


class PatientSortOption(str):
    NEWEST = "newest"
    OLDEST = "oldest"
    ALPHABETICAL = "alphabetical"
    RECENTLY_VISITED = "recently_visited"


class PatientSearchParams(BaseModel):
    """Typed view of the query params accepted by GET /patients. The router
    builds this from FastAPI `Query(...)` params so validation/defaults are
    centralized in one place for the repository layer to consume."""

    q: str | None = None
    branch_id: UUID | None = None
    gender: Gender | None = None
    status: PatientStatus | None = None
    age_min: int | None = Field(default=None, ge=0, le=150)
    age_max: int | None = Field(default=None, ge=0, le=150)
    registered_from: date | None = None
    registered_to: date | None = None
    last_visit_from: date | None = None
    last_visit_to: date | None = None
    sort: str = "newest"
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class PatientListResponse(BaseModel):
    items: list[PatientListItem]
    total: int
    limit: int
    offset: int


class DuplicateCandidate(BaseModel):
    id: UUID
    patient_number: str
    full_name: str
    birth_date: date
    mobile_number: str
    match_reason: str


class PatientCreateResponse(BaseModel):
    """Returned by POST /patients. `patient` is None (and `duplicates`
    populated) when duplicates were found and the caller did not pass
    `override=true`."""

    patient: PatientRead | None = None
    duplicates: list[DuplicateCandidate] = Field(default_factory=list)

    @property
    def has_duplicates(self) -> bool:
        return bool(self.duplicates)


class PatientQrResponse(BaseModel):
    patient_id: UUID
    qr_code: str
    # The actual QR image is not rendered server-side in this phase - see
    # `docs/DATABASE.md` ("QR code approach") for the documented rationale.
    payload: str


class PatientPhotoUploadResponse(BaseModel):
    """Presigned-URL stub for Supabase Storage upload. See TODO in
    `services/patient_service.py::request_photo_upload_url`.
    """

    upload_url: str
    public_url: str
    expires_in: int
