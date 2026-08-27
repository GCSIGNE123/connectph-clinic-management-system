"""Pydantic schemas for Clinical Consultation / SOAP (Phase 8)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.consultation import ConsultationStatus
from app.models.consultation_attachment import AttachmentType
from app.models.diagnosis import DiagnosisStatus, DiagnosisType
from app.schemas.doctor_workspace import LockInfo
from app.schemas.visit import VisitTimelineEventRead


class SoapNoteUpsert(BaseModel):
    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    past_medical_history: str | None = None
    family_history: str | None = None
    social_history: str | None = None
    review_of_systems: str | None = None
    subjective_notes: str | None = None

    blood_pressure: str | None = None
    pulse_rate: int | None = None
    respiratory_rate: int | None = None
    temperature: float | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    oxygen_saturation: float | None = None
    pain_score: int | None = None
    head_circumference_cm: float | None = None
    physical_examination: str | None = None
    clinical_findings: str | None = None

    clinical_impression: str | None = None
    differential_diagnosis: str | None = None
    assessment_notes: str | None = None

    treatment_plan: str | None = None
    patient_instructions: str | None = None
    followup_recommendation: str | None = None
    referral_notes: str | None = None


class SoapNoteRead(SoapNoteUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    bmi: float | None = None
    updated_at: datetime


class SoapNoteSubjectiveObjectiveUpsert(BaseModel):
    """Phase 20 (items 4-5): the narrow field set a Receptionist/Nurse may
    write via `PUT /consultations/{id}/soap/subjective-objective` - the
    Subjective section plus Objective/vitals. Assessment and Plan are
    deliberately absent from this schema; they can only be reached via the
    full `SoapNoteUpsert`/`save_soap` path, gated by
    `require_consultation_edit_role` (Doctor/Owner/Administrator only)."""

    chief_complaint: str | None = None
    history_of_present_illness: str | None = None
    past_medical_history: str | None = None
    family_history: str | None = None
    social_history: str | None = None
    review_of_systems: str | None = None
    subjective_notes: str | None = None

    blood_pressure: str | None = None
    pulse_rate: int | None = None
    respiratory_rate: int | None = None
    temperature: float | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    oxygen_saturation: float | None = None
    pain_score: int | None = None
    head_circumference_cm: float | None = None
    physical_examination: str | None = None
    clinical_findings: str | None = None


class SoapNoteSubjectiveObjectiveRead(SoapNoteSubjectiveObjectiveUpsert):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    bmi: float | None = None
    updated_at: datetime


class ConsultationCompleteRequest(BaseModel):
    """Phase 20 (item 9): optional body for `POST /consultations/{id}/complete`
    letting the Doctor set/override the consultation fee that flows into the
    auto-created invoice, instead of it only ever coming from
    `Doctor.consultation_fee`/`ClinicService.default_price` at the billing
    stage. Omitting the body (or `consultation_fee`) preserves the exact
    pre-Phase-20 pricing behavior."""

    consultation_fee: float | None = Field(default=None, ge=0)


class DiagnosisCreate(BaseModel):
    diagnosis_type: DiagnosisType
    status: DiagnosisStatus = DiagnosisStatus.WORKING
    notes: str | None = Field(default=None, max_length=2000)
    icd10_code: str | None = Field(default=None, max_length=20)
    icd10_description: str | None = Field(default=None, max_length=255)


class DiagnosisUpdate(BaseModel):
    diagnosis_type: DiagnosisType | None = None
    status: DiagnosisStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)
    icd10_code: str | None = Field(default=None, max_length=20)
    icd10_description: str | None = Field(default=None, max_length=255)


class DiagnosisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    diagnosis_type: DiagnosisType
    status: DiagnosisStatus
    notes: str | None = None
    icd10_code: str | None = None
    icd10_description: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    attachment_type: AttachmentType
    file_name: str
    file_url: str
    file_size_bytes: int | None = None
    uploaded_by: UUID | None = None
    created_at: datetime


class ConsultationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    visit_id: UUID
    branch_id: UUID
    doctor_id: UUID
    patient_id: UUID
    status: ConsultationStatus
    started_at: datetime
    completed_at: datetime | None = None
    signed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConsultationDetail(ConsultationRead):
    doctor_name: str | None = None
    doctor_prc_license: str | None = None
    doctor_ptr_number: str | None = None
    # Fully resolved (see `Doctor.effective_workspace_config`) - drives
    # which consultation sections the frontend shows/hides and marks
    # required for THIS doctor. Never null - a doctor with no custom
    # config still resolves to "every section visible, none required".
    doctor_workspace_config: dict = Field(default_factory=dict)
    patient_name: str | None = None
    patient_number: str | None = None
    visit_number: str | None = None
    soap_note: SoapNoteRead | None = None
    diagnoses: list[DiagnosisRead] = Field(default_factory=list)
    attachments: list[AttachmentRead] = Field(default_factory=list)
    lock: LockInfo


class ConsultationTimelineResponse(BaseModel):
    visit_id: UUID
    events: list[VisitTimelineEventRead]
