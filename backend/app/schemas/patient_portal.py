"""Pydantic schemas for the Patient Portal (Phase 18)."""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# --- Auth ---

class PatientLoginRequest(BaseModel):
    identifier: str = Field(..., description="Email or mobile number")
    password: str


class PatientTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    patient_id: UUID


class PatientRefreshRequest(BaseModel):
    refresh_token: str


class PatientForgotPasswordRequest(BaseModel):
    identifier: str


class PatientResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class PatientChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# --- Profile ---

class PatientProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str
    middle_name: str | None
    last_name: str
    mobile_number: str
    telephone_number: str | None
    email: str | None
    address_line: str | None
    barangay: str | None
    city: str | None
    province: str | None
    zip_code: str | None
    photo_url: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None
    is_email_verified: bool
    last_login_at: datetime | None


class PatientProfileUpdateRequest(BaseModel):
    mobile_number: str | None = None
    telephone_number: str | None = None
    email: str | None = None
    address_line: str | None = None
    barangay: str | None = None
    city: str | None = None
    province: str | None = None
    zip_code: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None


class PatientNotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    appointment_reminders: bool
    lab_result_alerts: bool
    billing_notices: bool
    clinic_announcements: bool
    preferred_channel: str


class PatientNotificationPreferenceUpdateRequest(BaseModel):
    appointment_reminders: bool | None = None
    lab_result_alerts: bool | None = None
    billing_notices: bool | None = None
    clinic_announcements: bool | None = None


# --- Dashboard ---

class DashboardAppointmentSummary(BaseModel):
    id: UUID
    appointment_number: str
    appointment_date: date
    start_time: time
    status: str
    doctor_name: str | None


class DashboardVisitSummary(BaseModel):
    id: UUID
    visit_number: str
    visit_date: date
    status: str


class DashboardLabSummary(BaseModel):
    id: UUID
    test_type: str
    released_at: datetime | None


class DashboardPrescriptionSummary(BaseModel):
    id: UUID
    prescription_number: str
    created_at: datetime
    item_count: int


class PatientDashboardResponse(BaseModel):
    upcoming_appointments: list[DashboardAppointmentSummary]
    recent_visits: list[DashboardVisitSummary]
    outstanding_balance: Decimal
    latest_lab_results: list[DashboardLabSummary]
    recent_prescriptions: list[DashboardPrescriptionSummary]
    announcements: list[str] = Field(
        default_factory=lambda: ["Clinic announcements are not yet configured for this clinic."]
    )


# --- Appointments ---

class PatientAppointmentResponse(BaseModel):
    id: UUID
    appointment_number: str
    appointment_type: str
    appointment_date: date
    start_time: time
    end_time: time
    status: str
    doctor_id: UUID | None = None
    doctor_name: str | None
    department_name: str | None
    notes: str | None


# --- Laboratory ---

class PatientLabResultParam(BaseModel):
    parameter_name: str
    result_type: str
    numeric_value: Decimal | None
    text_value: str | None
    normal_range: str | None
    units: str | None
    interpretation: str | None


class PatientLabOrderResponse(BaseModel):
    id: UUID
    test_type: str
    status: str
    released_at: datetime | None
    results: list[PatientLabResultParam]
    pdf_available: bool = False


# --- Prescriptions ---

class PatientPrescriptionItemResponse(BaseModel):
    medicine: str
    generic_name: str | None
    brand_name: str | None
    strength: str | None
    dosage: str | None
    frequency: str | None
    duration: str | None
    quantity: str | None
    instructions: str | None


class PatientPrescriptionResponse(BaseModel):
    id: UUID
    prescription_number: str
    status: str
    created_at: datetime
    doctor_name: str | None
    is_current: bool
    items: list[PatientPrescriptionItemResponse]


# --- Medical records ---

class PatientVisibleDiagnosis(BaseModel):
    id: UUID
    diagnosis_type: str
    status: str
    notes: str | None
    icd10_code: str | None
    icd10_description: str | None


class PatientVisibleAttachment(BaseModel):
    id: UUID
    attachment_type: str
    file_name: str
    file_url: str


class PatientMedicalRecordResponse(BaseModel):
    consultation_id: UUID
    visit_date: date
    doctor_name: str | None
    diagnoses: list[PatientVisibleDiagnosis]
    attachments: list[PatientVisibleAttachment]


# --- Billing ---

class PatientInvoiceItemResponse(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class PatientPaymentResponse(BaseModel):
    id: UUID
    payment_method: str
    amount: Decimal
    status: str
    paid_at: datetime


class PatientInvoiceResponse(BaseModel):
    id: UUID
    invoice_number: str
    invoice_date: date
    status: str
    subtotal: Decimal
    discount_total: Decimal
    grand_total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    items: list[PatientInvoiceItemResponse]
    payments: list[PatientPaymentResponse]


class PatientBillingSummaryResponse(BaseModel):
    outstanding_balance: Decimal
    invoices: list[PatientInvoiceResponse]


# --- Appointment booking (Phase 19) ---

class PatientBranchOption(BaseModel):
    id: UUID
    name: str
    address: str | None = None


class PatientDepartmentOption(BaseModel):
    id: UUID
    name: str


class PatientDoctorOption(BaseModel):
    id: UUID
    full_name: str
    specialization: str | None = None
    department_id: UUID | None = None
    branch_id: UUID | None = None


class PatientAvailableDatesResponse(BaseModel):
    doctor_id: UUID
    dates: list[date]


class PatientTimeSlot(BaseModel):
    start_time: time
    end_time: time


class PatientAvailableSlotsResponse(BaseModel):
    doctor_id: UUID
    date: date
    slots: list[PatientTimeSlot]


class PatientAppointmentCreateRequest(BaseModel):
    branch_id: UUID
    doctor_id: UUID
    department_id: UUID | None = None
    service_id: UUID | None = None
    appointment_type: str = "NewConsultation"
    appointment_date: date
    start_time: time
    notes: str | None = Field(default=None, max_length=1000)


class PatientAppointmentDetailResponse(BaseModel):
    id: UUID
    appointment_number: str
    appointment_type: str
    appointment_date: date
    start_time: time
    end_time: time
    status: str
    doctor_name: str | None = None
    department_name: str | None = None
    branch_name: str | None = None
    notes: str | None = None


class PatientAppointmentRescheduleRequest(BaseModel):
    appointment_date: date
    start_time: time
    reason: str | None = Field(default=None, max_length=500)


class PatientAppointmentCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# --- Notifications ---

class PatientNotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    notification_type: str
    title: str
    body: str | None
    is_read: bool
    created_at: datetime
