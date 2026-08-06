"""Patient Portal API - genuinely separate router module (Phase 18).

Every route here is prefixed `/api/v1/patient-portal/...`. All non-auth
routes are gated by `get_current_patient` (see `app/core/dependencies.py`) -
NEVER by `get_current_user`/`require_roles` (clinic staff) or
`get_current_platform_admin` (Phase 15). A clinic-staff or platform-admin
JWT presented here gets a clean 401 (wrong token `type`/missing
`patient_account_id`+`patient_id` claims - see `app/core/patient_security.py`).

Every query is scoped by `current.patient.id` (== `current.id`) AND
`current.patient.clinic_id` (== `current.clinic_id`), both taken from the
verified token via `CurrentPatient`, never from a path/query/body param -
this is the mechanism that proves patient-to-patient and
patient-to-clinic isolation (see `app/tests/test_patient_portal.py`).
"""

import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import CurrentPatient, get_current_patient, get_db
from app.models.patient_account import PatientAccount
from app.schemas.patient_portal import (
    DashboardAppointmentSummary,
    DashboardLabSummary,
    DashboardPrescriptionSummary,
    DashboardVisitSummary,
    PatientAppointmentResponse,
    PatientBillingSummaryResponse,
    PatientChangePasswordRequest,
    PatientDashboardResponse,
    PatientForgotPasswordRequest,
    PatientInvoiceItemResponse,
    PatientInvoiceResponse,
    PatientLabOrderResponse,
    PatientLabResultParam,
    PatientLoginRequest,
    PatientMedicalRecordResponse,
    PatientNotificationPreferenceResponse,
    PatientNotificationPreferenceUpdateRequest,
    PatientNotificationResponse,
    PatientPaymentResponse,
    PatientPrescriptionItemResponse,
    PatientPrescriptionResponse,
    PatientProfileResponse,
    PatientProfileUpdateRequest,
    PatientRefreshRequest,
    PatientResetPasswordRequest,
    PatientTokenResponse,
    PatientVisibleAttachment,
    PatientVisibleDiagnosis,
)
from app.services.patient_auth_service import PatientAuthService
from app.services.patient_portal_service import PatientPortalService

from app.api.v1.patient_portal.appointments import router as appointments_booking_router

router = APIRouter(prefix="/patient-portal", tags=["patient-portal"])
router.include_router(appointments_booking_router)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------


@router.post("/auth/login", response_model=PatientTokenResponse)
async def patient_login(payload: PatientLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = PatientAuthService(db)
    result = await service.login(
        identifier=payload.identifier, password=payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return PatientTokenResponse(access_token=result.access_token, refresh_token=result.refresh_token, patient_id=result.patient.id)


@router.post("/auth/refresh", response_model=PatientTokenResponse)
async def patient_refresh(payload: PatientRefreshRequest, db: AsyncSession = Depends(get_db)):
    service = PatientAuthService(db)
    result = await service.refresh(payload.refresh_token)
    return PatientTokenResponse(access_token=result.access_token, refresh_token=result.refresh_token, patient_id=result.patient.id)


@router.post("/auth/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def patient_forgot_password(payload: PatientForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    service = PatientAuthService(db)
    await service.forgot_password(payload.identifier)
    return {"detail": "If an account exists, a reset link has been sent."}


@router.post("/auth/reset-password")
async def patient_reset_password(payload: PatientResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    service = PatientAuthService(db)
    await service.reset_password(payload.token, payload.new_password)
    return {"detail": "Password has been reset."}


@router.post("/auth/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def patient_change_password(
    payload: PatientChangePasswordRequest,
    current: CurrentPatient = Depends(get_current_patient),
    db: AsyncSession = Depends(get_db),
):
    service = PatientAuthService(db)
    await service.change_password(account=current.account, old_password=payload.old_password, new_password=payload.new_password)
    from app.models.audit_log import AuditLog  # noqa: PLC0415

    db.add(AuditLog(
        clinic_id=current.clinic_id, user_id=None, action="patient.password_change",
        entity_type="patient", entity_id=str(current.id), metadata_json={"principal": "patient"},
    ))
    await db.commit()


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


@router.get("/profile", response_model=PatientProfileResponse)
async def get_profile(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    service = PatientPortalService(db)
    patient = await service.get_profile(patient_id=current.id, clinic_id=current.clinic_id)
    return PatientProfileResponse(
        id=patient.id, first_name=patient.first_name, middle_name=patient.middle_name, last_name=patient.last_name,
        mobile_number=patient.mobile_number, telephone_number=patient.telephone_number, email=patient.email,
        address_line=patient.address_line, barangay=patient.barangay, city=patient.city, province=patient.province,
        zip_code=patient.zip_code, photo_url=patient.photo_url,
        emergency_contact_name=patient.emergency_contact_name, emergency_contact_phone=patient.emergency_contact_phone,
        is_email_verified=current.account.is_email_verified, last_login_at=current.account.last_login_at,
    )


@router.put("/profile", response_model=PatientProfileResponse)
async def update_profile(
    payload: PatientProfileUpdateRequest, request: Request,
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    service = PatientPortalService(db)
    patient = await service.update_profile(
        patient_id=current.id, clinic_id=current.clinic_id, account=current.account,
        updates=payload.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    return PatientProfileResponse(
        id=patient.id, first_name=patient.first_name, middle_name=patient.middle_name, last_name=patient.last_name,
        mobile_number=patient.mobile_number, telephone_number=patient.telephone_number, email=patient.email,
        address_line=patient.address_line, barangay=patient.barangay, city=patient.city, province=patient.province,
        zip_code=patient.zip_code, photo_url=patient.photo_url,
        emergency_contact_name=patient.emergency_contact_name, emergency_contact_phone=patient.emergency_contact_phone,
        is_email_verified=current.account.is_email_verified, last_login_at=current.account.last_login_at,
    )


@router.post("/profile/photo")
async def request_photo_upload(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    """Same presigned-URL stub pattern as the clinic-staff Patient Management
    upload (`PatientService.request_photo_upload_url`) - no Supabase project
    provisioned yet in dev. See that method's TODO."""
    token = secrets.token_urlsafe(24)
    object_path = f"clinics/{current.clinic_id}/patients/{current.id}/photo-{token}.jpg"
    public_url = f"https://stub.supabase.local/storage/v1/object/public/{object_path}"
    service = PatientPortalService(db)
    await service.update_photo(patient_id=current.id, clinic_id=current.clinic_id, photo_url=public_url)
    return {
        "upload_url": f"https://stub.supabase.local/storage/v1/upload/{object_path}",
        "public_url": public_url,
        "expires_in": 600,
    }


@router.get("/notification-preferences", response_model=PatientNotificationPreferenceResponse)
async def get_notification_preferences(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    service = PatientPortalService(db)
    pref = await service.get_notification_preferences(patient_id=current.id, clinic_id=current.clinic_id)
    return PatientNotificationPreferenceResponse(
        appointment_reminders=pref.appointment_reminders, lab_result_alerts=pref.lab_result_alerts,
        billing_notices=pref.billing_notices, clinic_announcements=pref.clinic_announcements,
        preferred_channel=pref.preferred_channel.value,
    )


@router.put("/notification-preferences", response_model=PatientNotificationPreferenceResponse)
async def update_notification_preferences(
    payload: PatientNotificationPreferenceUpdateRequest,
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    service = PatientPortalService(db)
    pref = await service.update_notification_preferences(
        patient_id=current.id, clinic_id=current.clinic_id, updates=payload.model_dump(exclude_unset=True)
    )
    return PatientNotificationPreferenceResponse(
        appointment_reminders=pref.appointment_reminders, lab_result_alerts=pref.lab_result_alerts,
        billing_notices=pref.billing_notices, clinic_announcements=pref.clinic_announcements,
        preferred_channel=pref.preferred_channel.value,
    )


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


@router.get("/dashboard", response_model=PatientDashboardResponse)
async def get_dashboard(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    service = PatientPortalService(db)
    data = await service.get_dashboard(patient_id=current.id, clinic_id=current.clinic_id)
    return PatientDashboardResponse(
        upcoming_appointments=[DashboardAppointmentSummary(**a) for a in data["upcoming_appointments"]],
        recent_visits=[DashboardVisitSummary(**v) for v in data["recent_visits"]],
        outstanding_balance=data["outstanding_balance"],
        latest_lab_results=[DashboardLabSummary(**l) for l in data["latest_lab_results"]],
        recent_prescriptions=[DashboardPrescriptionSummary(**p) for p in data["recent_prescriptions"]],
    )


# --------------------------------------------------------------------------
# Appointments (view-only)
# --------------------------------------------------------------------------


@router.get("/appointments", response_model=list[PatientAppointmentResponse])
async def list_appointments(
    tab: str | None = Query(default=None, description="upcoming|completed|cancelled|rescheduled"),
    current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db),
):
    service = PatientPortalService(db)
    rows = await service.list_appointments(patient_id=current.id, clinic_id=current.clinic_id, tab=tab)
    return [
        PatientAppointmentResponse(
            id=a.id, appointment_number=a.appointment_number, appointment_type=a.appointment_type.value,
            appointment_date=a.appointment_date, start_time=a.start_time, end_time=a.end_time,
            status=a.status.value, doctor_id=a.doctor_id, doctor_name=a.doctor.full_name if a.doctor else None,
            department_name=a.department.name if a.department else None, notes=a.notes,
        )
        for a in rows
    ]


# --------------------------------------------------------------------------
# Laboratory - Released only
# --------------------------------------------------------------------------


@router.get("/laboratory", response_model=list[PatientLabOrderResponse])
async def list_lab_results(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    service = PatientPortalService(db)
    orders = await service.list_lab_orders(patient_id=current.id, clinic_id=current.clinic_id)
    return [_lab_order_to_schema(o) for o in orders]


@router.get("/laboratory/{lab_order_id}", response_model=PatientLabOrderResponse)
async def get_lab_result(
    lab_order_id: UUID, current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
):
    service = PatientPortalService(db)
    order = await service.get_lab_order(patient_id=current.id, clinic_id=current.clinic_id, lab_order_id=lab_order_id)
    return _lab_order_to_schema(order)


@router.get("/laboratory/{lab_order_id}/pdf")
async def download_lab_pdf(
    lab_order_id: UUID, current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
):
    """No existing lab-result PDF/export mechanism exists to reuse (see
    `app/models/laboratory_attachment.py` - attachments are staff-uploaded
    scans/images, not a generated results PDF) - per phase scope, a
    placeholder response is returned rather than building new PDF
    generation."""
    service = PatientPortalService(db)
    await service.get_lab_order(patient_id=current.id, clinic_id=current.clinic_id, lab_order_id=lab_order_id)
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="No PDF available for this result yet.")


def _lab_order_to_schema(o) -> PatientLabOrderResponse:
    return PatientLabOrderResponse(
        id=o.id, test_type=o.test_type, status=o.status.value, released_at=o.released_at,
        results=[
            PatientLabResultParam(
                parameter_name=r.parameter_name, result_type=r.result_type.value, numeric_value=r.numeric_value,
                text_value=r.text_value, normal_range=r.normal_range, units=r.units,
                interpretation=r.interpretation.value if r.interpretation else None,
            )
            for r in o.results
        ],
        pdf_available=False,
    )


# --------------------------------------------------------------------------
# Prescriptions (view-only)
# --------------------------------------------------------------------------


@router.get("/prescriptions", response_model=list[PatientPrescriptionResponse])
async def list_prescriptions(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    from app.models.prescription import PrescriptionStatus  # noqa: PLC0415

    service = PatientPortalService(db)
    rows = await service.list_prescriptions(patient_id=current.id, clinic_id=current.clinic_id)
    return [
        PatientPrescriptionResponse(
            id=p.id, prescription_number=p.prescription_number, status=p.status.value, created_at=p.created_at,
            doctor_name=p.doctor.full_name if p.doctor else None,
            is_current=p.status == PrescriptionStatus.FINALIZED,
            items=[
                PatientPrescriptionItemResponse(
                    medicine=i.medicine, generic_name=i.generic_name, brand_name=i.brand_name, strength=i.strength,
                    dosage=i.dosage, frequency=i.frequency, duration=i.duration, quantity=i.quantity,
                    instructions=i.instructions,
                )
                for i in p.items
            ],
        )
        for p in rows
    ]


# --------------------------------------------------------------------------
# Medical records (read-only, patient_visible only)
# --------------------------------------------------------------------------


@router.get("/medical-records", response_model=list[PatientMedicalRecordResponse])
async def list_medical_records(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    service = PatientPortalService(db)
    records = await service.list_medical_records(patient_id=current.id, clinic_id=current.clinic_id)
    return [
        PatientMedicalRecordResponse(
            consultation_id=r["consultation_id"], visit_date=r["visit_date"], doctor_name=r["doctor_name"],
            diagnoses=[
                PatientVisibleDiagnosis(
                    id=d.id, diagnosis_type=d.diagnosis_type.value, status=d.status.value, notes=d.notes,
                    icd10_code=d.icd10_code, icd10_description=d.icd10_description,
                )
                for d in r["diagnoses"]
            ],
            attachments=[
                PatientVisibleAttachment(id=a.id, attachment_type=a.attachment_type.value, file_name=a.file_name, file_url=a.file_url)
                for a in r["attachments"]
            ],
        )
        for r in records
    ]


# --------------------------------------------------------------------------
# Billing (read-only)
# --------------------------------------------------------------------------


@router.get("/billing", response_model=PatientBillingSummaryResponse)
async def get_billing(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    service = PatientPortalService(db)
    invoices = await service.list_invoices(patient_id=current.id, clinic_id=current.clinic_id)
    balance = await service.outstanding_balance(patient_id=current.id, clinic_id=current.clinic_id)
    return PatientBillingSummaryResponse(
        outstanding_balance=balance,
        invoices=[
            PatientInvoiceResponse(
                id=inv.id, invoice_number=inv.invoice_number, invoice_date=inv.invoice_date, status=inv.status.value,
                subtotal=inv.subtotal, discount_total=inv.discount_total, grand_total=inv.grand_total,
                amount_paid=inv.amount_paid, balance_due=inv.balance_due,
                items=[
                    PatientInvoiceItemResponse(description=i.description, quantity=i.quantity, unit_price=i.unit_price, line_total=i.line_total)
                    for i in inv.items
                ],
                payments=[
                    PatientPaymentResponse(id=p.id, payment_method=p.payment_method.value, amount=p.amount, status=p.status.value, paid_at=p.paid_at)
                    for p in inv.payments
                ],
            )
            for inv in invoices
        ],
    )


# --------------------------------------------------------------------------
# Notifications (read-only in-app feed)
# --------------------------------------------------------------------------


@router.get("/notifications", response_model=list[PatientNotificationResponse])
async def list_notifications(current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)):
    service = PatientPortalService(db)
    rows = await service.list_notifications(patient_id=current.id, clinic_id=current.clinic_id)
    return [
        PatientNotificationResponse(
            id=n.id, notification_type=n.notification_type.value, title=n.title, body=n.body,
            is_read=n.is_read, created_at=n.created_at,
        )
        for n in rows
    ]


@router.post("/notifications/{notification_id}/read", response_model=PatientNotificationResponse)
async def mark_notification_read(
    notification_id: UUID, current: CurrentPatient = Depends(get_current_patient), db: AsyncSession = Depends(get_db)
):
    service = PatientPortalService(db)
    n = await service.mark_notification_read(patient_id=current.id, clinic_id=current.clinic_id, notification_id=notification_id)
    return PatientNotificationResponse(
        id=n.id, notification_type=n.notification_type.value, title=n.title, body=n.body,
        is_read=n.is_read, created_at=n.created_at,
    )
