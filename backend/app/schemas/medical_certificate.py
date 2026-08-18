"""Pydantic schemas for Medical Certificates."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.medical_certificate import MedicalCertificateStatus, MedicalCertificateType


class MedicalCertificateCreate(BaseModel):
    """Creates a Draft. Findings pre-filled client-side from the
    consultation's Diagnosis records (a one-time text snapshot, not a live
    reference - see the model's module docstring) but the doctor may edit
    it here before saving."""

    certificate_type: MedicalCertificateType
    findings: str | None = None
    recommendation: str | None = None
    rest_days: int | None = Field(default=None, ge=0)
    date_from: date | None = None
    date_to: date | None = None
    notes: str | None = None


class MedicalCertificateUpdate(BaseModel):
    """Edits a Draft only - the service layer rejects this for any
    non-Draft certificate. Every field optional so the frontend can send a
    partial patch as the doctor types."""

    certificate_type: MedicalCertificateType | None = None
    findings: str | None = None
    recommendation: str | None = None
    rest_days: int | None = Field(default=None, ge=0)
    date_from: date | None = None
    date_to: date | None = None
    notes: str | None = None


class MedicalCertificateCancel(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class MedicalCertificateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    visit_id: UUID
    patient_id: UUID
    doctor_id: UUID
    certificate_number: str | None = None
    certificate_type: MedicalCertificateType
    status: MedicalCertificateStatus
    findings: str | None = None
    recommendation: str | None = None
    rest_days: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    notes: str | None = None
    issued_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_reason: str | None = None
    cancelled_by: UUID | None = None
    superseded_by_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class MedicalCertificateDetail(MedicalCertificateRead):
    """Adds the live-pulled display fields the print template needs -
    never stored on the row itself (see model docstring)."""

    patient_name: str | None = None
    patient_age: int | None = None
    patient_sex: str | None = None
    doctor_name: str | None = None
    doctor_prc_license: str | None = None
    doctor_ptr_number: str | None = None
    clinic_name: str | None = None
    clinic_logo_url: str | None = None
    clinic_address: str | None = None
    clinic_license_number: str | None = None
    visit_number: str | None = None
