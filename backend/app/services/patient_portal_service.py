"""Patient Portal read/profile service (Phase 18).

CRITICAL isolation rule: every query method below takes `patient_id` and
`clinic_id` as explicit arguments supplied by the caller from the verified
JWT (`CurrentPatient`, see `app/core/dependencies.py`) - NEVER from a
request body/query param - and every query filters by BOTH. This is what
proves Patient A cannot read Patient B's data (even within the same clinic)
and cannot read another clinic's data.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_password
from app.models.appointment import Appointment, AppointmentStatus
from app.models.audit_log import AuditLog
from app.models.consultation import Consultation
from app.models.consultation_attachment import ConsultationAttachment
from app.models.diagnosis import Diagnosis
from app.models.doctor import Doctor
from app.models.invoice import Invoice
from app.models.laboratory_order import LaboratoryOrder, LaboratoryOrderStatus
from app.models.laboratory_result import LaboratoryResult
from app.models.patient import Patient
from app.models.patient_account import (
    PatientAccount,
    PatientNotification,
    PatientNotificationPreference,
)
from app.models.payment import Payment
from app.models.prescription import Prescription
from app.models.visit import Visit


class PatientPortalService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------

    async def get_profile(self, *, patient_id: UUID, clinic_id: UUID) -> Patient:
        patient = await self._get_patient_or_404(patient_id, clinic_id)
        return patient

    async def update_profile(
        self, *, patient_id: UUID, clinic_id: UUID, account: PatientAccount, updates: dict, ip_address: str | None
    ) -> Patient:
        patient = await self._get_patient_or_404(patient_id, clinic_id)
        for key, value in updates.items():
            if value is not None:
                setattr(patient, key, value)
        await self.session.flush()
        self.session.add(
            AuditLog(
                clinic_id=clinic_id, user_id=None, action="patient.profile_update",
                entity_type="patient", entity_id=str(patient_id), ip_address=ip_address,
                metadata_json={"principal": "patient", "fields": list(updates.keys())},
            )
        )
        await self.session.commit()
        return patient

    async def update_photo(self, *, patient_id: UUID, clinic_id: UUID, photo_url: str) -> Patient:
        patient = await self._get_patient_or_404(patient_id, clinic_id)
        patient.photo_url = photo_url
        await self.session.commit()
        return patient

    async def get_notification_preferences(self, *, patient_id: UUID, clinic_id: UUID) -> PatientNotificationPreference:
        result = await self.session.execute(
            select(PatientNotificationPreference).where(PatientNotificationPreference.patient_id == patient_id)
        )
        pref = result.scalar_one_or_none()
        if pref is None:
            pref = PatientNotificationPreference(patient_id=patient_id, clinic_id=clinic_id)
            self.session.add(pref)
            await self.session.commit()
            await self.session.refresh(pref)
        return pref

    async def update_notification_preferences(self, *, patient_id: UUID, clinic_id: UUID, updates: dict) -> PatientNotificationPreference:
        pref = await self.get_notification_preferences(patient_id=patient_id, clinic_id=clinic_id)
        for key, value in updates.items():
            if value is not None:
                setattr(pref, key, value)
        await self.session.commit()
        return pref

    async def _get_patient_or_404(self, patient_id: UUID, clinic_id: UUID) -> Patient:
        result = await self.session.execute(
            select(Patient).where(Patient.id == patient_id, Patient.clinic_id == clinic_id, Patient.is_deleted.is_(False))
        )
        patient = result.scalar_one_or_none()
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient record not found")
        return patient

    # ------------------------------------------------------------------
    # Appointments
    # ------------------------------------------------------------------

    async def list_appointments(self, *, patient_id: UUID, clinic_id: UUID, tab: str | None = None) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.clinic_id == clinic_id,
                Appointment.is_deleted.is_(False),
            )
            .options(selectinload(Appointment.doctor), selectinload(Appointment.department))
            .order_by(Appointment.appointment_date.desc(), Appointment.start_time.desc())
        )
        rows = list((await self.session.execute(stmt)).scalars().all())
        if tab is None or tab.lower() == "all":
            return rows
        tab_map = {
            "upcoming": {AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED, AppointmentStatus.CHECKED_IN, AppointmentStatus.WAITING, AppointmentStatus.IN_CONSULTATION},
            "completed": {AppointmentStatus.COMPLETED},
            "cancelled": {AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW},
            "rescheduled": {AppointmentStatus.RESCHEDULED},
        }
        wanted = tab_map.get(tab.lower())
        if wanted is None:
            return rows
        return [a for a in rows if a.status in wanted]

    # ------------------------------------------------------------------
    # Laboratory - Released only, per spec.
    # ------------------------------------------------------------------

    async def list_lab_orders(self, *, patient_id: UUID, clinic_id: UUID) -> list[LaboratoryOrder]:
        stmt = (
            select(LaboratoryOrder)
            .where(
                LaboratoryOrder.patient_id == patient_id,
                LaboratoryOrder.clinic_id == clinic_id,
                LaboratoryOrder.status == LaboratoryOrderStatus.RELEASED,
                LaboratoryOrder.is_deleted.is_(False),
            )
            .options(selectinload(LaboratoryOrder.results))
            .order_by(LaboratoryOrder.released_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_lab_order(self, *, patient_id: UUID, clinic_id: UUID, lab_order_id: UUID) -> LaboratoryOrder:
        stmt = (
            select(LaboratoryOrder)
            .where(
                LaboratoryOrder.id == lab_order_id,
                LaboratoryOrder.patient_id == patient_id,
                LaboratoryOrder.clinic_id == clinic_id,
                LaboratoryOrder.status == LaboratoryOrderStatus.RELEASED,
            )
            .options(selectinload(LaboratoryOrder.results))
        )
        order = (await self.session.execute(stmt)).scalar_one_or_none()
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab result not found")
        return order

    # ------------------------------------------------------------------
    # Prescriptions
    # ------------------------------------------------------------------

    async def list_prescriptions(self, *, patient_id: UUID, clinic_id: UUID) -> list[Prescription]:
        stmt = (
            select(Prescription)
            .where(
                Prescription.patient_id == patient_id,
                Prescription.clinic_id == clinic_id,
                Prescription.is_deleted.is_(False),
            )
            .options(selectinload(Prescription.items), selectinload(Prescription.doctor))
            .order_by(Prescription.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # Medical records - only patient_visible=True Diagnoses/Attachments.
    # ------------------------------------------------------------------

    async def list_medical_records(self, *, patient_id: UUID, clinic_id: UUID) -> list[dict]:
        visit_stmt = select(Visit).where(
            Visit.patient_id == patient_id, Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False)
        )
        visits = list((await self.session.execute(visit_stmt)).scalars().all())
        visit_ids = [v.id for v in visits]
        if not visit_ids:
            return []

        consult_stmt = (
            select(Consultation)
            .where(Consultation.visit_id.in_(visit_ids), Consultation.clinic_id == clinic_id)
            .options(selectinload(Consultation.doctor))
        )
        consultations = list((await self.session.execute(consult_stmt)).scalars().all())
        visit_by_id = {v.id: v for v in visits}

        results = []
        for c in consultations:
            diag_stmt = select(Diagnosis).where(
                Diagnosis.consultation_id == c.id, Diagnosis.patient_visible.is_(True), Diagnosis.is_deleted.is_(False)
            )
            diagnoses = list((await self.session.execute(diag_stmt)).scalars().all())
            att_stmt = select(ConsultationAttachment).where(
                ConsultationAttachment.consultation_id == c.id,
                ConsultationAttachment.patient_visible.is_(True),
                ConsultationAttachment.is_deleted.is_(False),
            )
            attachments = list((await self.session.execute(att_stmt)).scalars().all())
            if not diagnoses and not attachments:
                continue  # Nothing patient-visible for this consultation - hide it entirely.
            v = visit_by_id.get(c.visit_id)
            results.append(
                {
                    "consultation_id": c.id,
                    "visit_date": v.visit_date if v else None,
                    "doctor_name": c.doctor.full_name if c.doctor else None,
                    "diagnoses": diagnoses,
                    "attachments": attachments,
                }
            )
        results.sort(key=lambda r: r["visit_date"] or date.min, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Billing
    # ------------------------------------------------------------------

    async def list_invoices(self, *, patient_id: UUID, clinic_id: UUID) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .where(Invoice.patient_id == patient_id, Invoice.clinic_id == clinic_id, Invoice.is_deleted.is_(False))
            .options(selectinload(Invoice.items), selectinload(Invoice.payments))
            .order_by(Invoice.invoice_date.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def outstanding_balance(self, *, patient_id: UUID, clinic_id: UUID) -> Decimal:
        invoices = await self.list_invoices(patient_id=patient_id, clinic_id=clinic_id)
        return sum((inv.balance_due for inv in invoices), Decimal("0"))

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------

    async def list_notifications(self, *, patient_id: UUID, clinic_id: UUID) -> list[PatientNotification]:
        stmt = (
            select(PatientNotification)
            .where(PatientNotification.patient_id == patient_id, PatientNotification.clinic_id == clinic_id)
            .order_by(PatientNotification.created_at.desc())
            .limit(100)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def mark_notification_read(self, *, patient_id: UUID, clinic_id: UUID, notification_id: UUID) -> PatientNotification:
        stmt = select(PatientNotification).where(
            PatientNotification.id == notification_id,
            PatientNotification.patient_id == patient_id,
            PatientNotification.clinic_id == clinic_id,
        )
        notif = (await self.session.execute(stmt)).scalar_one_or_none()
        if notif is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        notif.is_read = True
        notif.read_at = datetime.now(UTC)
        await self.session.commit()
        return notif

    # ------------------------------------------------------------------
    # Dashboard (aggregates the above, all scoped identically)
    # ------------------------------------------------------------------

    async def get_dashboard(self, *, patient_id: UUID, clinic_id: UUID) -> dict:
        appts = await self.list_appointments(patient_id=patient_id, clinic_id=clinic_id, tab="upcoming")
        appts = sorted(appts, key=lambda a: (a.appointment_date, a.start_time))[:5]

        visit_stmt = (
            select(Visit)
            .where(Visit.patient_id == patient_id, Visit.clinic_id == clinic_id, Visit.is_deleted.is_(False))
            .order_by(Visit.visit_date.desc())
            .limit(5)
        )
        visits = list((await self.session.execute(visit_stmt)).scalars().all())

        balance = await self.outstanding_balance(patient_id=patient_id, clinic_id=clinic_id)

        labs = await self.list_lab_orders(patient_id=patient_id, clinic_id=clinic_id)
        labs = labs[:5]

        prescriptions = await self.list_prescriptions(patient_id=patient_id, clinic_id=clinic_id)
        prescriptions = prescriptions[:5]

        return {
            "upcoming_appointments": [
                {
                    "id": a.id, "appointment_number": a.appointment_number, "appointment_date": a.appointment_date,
                    "start_time": a.start_time, "status": a.status.value,
                    "doctor_name": a.doctor.full_name if a.doctor else None,
                }
                for a in appts
            ],
            "recent_visits": [
                {"id": v.id, "visit_number": v.visit_number, "visit_date": v.visit_date, "status": v.status.value}
                for v in visits
            ],
            "outstanding_balance": balance,
            "latest_lab_results": [
                {"id": lo.id, "test_type": lo.test_type, "released_at": lo.released_at} for lo in labs
            ],
            "recent_prescriptions": [
                {"id": p.id, "prescription_number": p.prescription_number, "created_at": p.created_at, "item_count": len(p.items)}
                for p in prescriptions
            ],
        }
