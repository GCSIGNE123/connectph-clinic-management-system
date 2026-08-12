"""Patient management service: create (with number generation + duplicate
detection + QR generation), update (with field-diff audit), archive/restore.

All operations are tenant-scoped (clinic_id) and write an audit log entry.
Patients are never hard-deleted - "archive" sets the business `status` to
Archived; soft-delete (`is_deleted`) is reserved for erroneous records and is
not exposed through the patient-facing API in this phase.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.patient import Patient, PatientStatus
from app.models.user import User
from app.repositories.patient_repository import PatientRepository
from app.schemas.patient import (
    DuplicateCandidate,
    PatientCreate,
    PatientCreateResponse,
    PatientRead,
    PatientSearchParams,
    PatientUpdate,
)
from app.services.audit_service import AuditService
from app.services.patient_number_generator import PatientNumberGenerator
from app.services import sync_queue_service


def _qr_payload(clinic_id: UUID, patient_id: UUID) -> str:
    """Build a signed, opaque QR payload for a patient.

    The payload embeds `clinic_id:patient_id` plus an HMAC-SHA256 signature
    (keyed with the app secret) so a future queue/appointment check-in scanner
    can verify the code was issued by this system without a DB round trip,
    while the raw string still stays free of any human-readable PII.

    Rendering an actual QR *image* is intentionally out of scope for this
    phase (no new heavy dependency has been vetted/added yet) - `GET
    /patients/{id}/qr` returns this payload string, and the frontend renders
    it as a QR code client-side (or a client-side `qrcode` library can be
    added later). See docs/DATABASE.md ("QR code approach").
    """
    message = f"{clinic_id}:{patient_id}".encode()
    secret_key = settings.JWT_SECRET_KEY.encode()
    signature = hmac.new(secret_key, message, hashlib.sha256).hexdigest()[:16]
    return f"{clinic_id}:{patient_id}:{signature}"


def _diff_fields(before: Patient, updates: dict) -> dict:
    changed = {}
    for field, new_value in updates.items():
        old_value = getattr(before, field, None)
        if isinstance(old_value, date) and isinstance(new_value, date):
            if old_value != new_value:
                changed[field] = {"from": str(old_value), "to": str(new_value)}
        elif old_value != new_value:
            changed[field] = {
                "from": str(old_value) if old_value is not None else None,
                "to": str(new_value) if new_value is not None else None,
            }
    return changed


class PatientService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.patient_repo = PatientRepository(session)
        self.number_generator = PatientNumberGenerator(session)
        self.audit_service = AuditService(session)

    async def check_duplicates(
        self,
        clinic_id: UUID,
        *,
        first_name: str,
        last_name: str,
        birth_date: date,
        mobile_number: str,
        exclude_id: UUID | None = None,
    ) -> list[DuplicateCandidate]:
        matches = await self.patient_repo.find_duplicates(
            clinic_id,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
            mobile_number=mobile_number,
            exclude_id=exclude_id,
        )
        return [
            DuplicateCandidate(
                id=patient.id,
                patient_number=patient.patient_number,
                full_name=patient.full_name,
                birth_date=patient.birth_date,
                mobile_number=patient.mobile_number,
                match_reason=reason,
            )
            for patient, reason in matches
        ]

    async def create_patient(
        self,
        payload: PatientCreate,
        *,
        clinic_id: UUID,
        actor: User,
        override_duplicate_warning: bool = False,
    ) -> PatientCreateResponse:
        if not override_duplicate_warning:
            duplicates = await self.check_duplicates(
                clinic_id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                birth_date=payload.birth_date,
                mobile_number=payload.mobile_number,
            )
            if duplicates:
                return PatientCreateResponse(patient=None, duplicates=duplicates)

        patient_number = await self.number_generator.next_number(clinic_id)
        today = datetime.now(UTC).date()

        patient = await self.patient_repo.create(
            clinic_id=clinic_id,
            branch_id=payload.branch_id,
            patient_number=patient_number,
            legacy_patient_id=payload.legacy_patient_id,
            first_name=payload.first_name,
            middle_name=payload.middle_name,
            last_name=payload.last_name,
            suffix=payload.suffix,
            birth_date=payload.birth_date,
            gender=payload.gender,
            civil_status=payload.civil_status,
            nationality=payload.nationality,
            address_line=payload.address_line,
            barangay=payload.barangay,
            city=payload.city,
            province=payload.province,
            zip_code=payload.zip_code,
            mobile_number=payload.mobile_number,
            telephone_number=payload.telephone_number,
            email=payload.email,
            occupation=payload.occupation,
            employer=payload.employer,
            blood_type=payload.blood_type,
            allergies=payload.allergies,
            medical_notes=payload.medical_notes,
            remarks=payload.remarks,
            photo_url=payload.photo_url,
            is_yakap_beneficiary=payload.is_yakap_beneficiary,
            status=PatientStatus.ACTIVE,
            date_registered=today,
            created_by=actor.id,
            updated_by=actor.id,
        )
        patient.qr_code = _qr_payload(clinic_id, patient.id)
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id,
            user_id=actor.id,
            action="patient.created",
            entity_type="patient",
            entity_id=str(patient.id),
            metadata={"patient_number": patient.patient_number},
        )
        await self.session.commit()

        refreshed = await self.patient_repo.get_by_id_and_clinic(patient.id, clinic_id)
        read = PatientRead.model_validate(refreshed)
        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort, never
        # affects this already-committed create (see sync_queue_service.py).
        await sync_queue_service.enqueue(
            entity_type="patient", record_id=refreshed.id, operation="create",
            payload=read.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return PatientCreateResponse(patient=read, duplicates=[])

    async def update_patient(
        self,
        patient_id: UUID,
        payload: PatientUpdate,
        *,
        clinic_id: UUID,
        actor: User,
        override_duplicate_warning: bool = False,
    ) -> PatientCreateResponse:
        patient = await self.patient_repo.get_by_id_and_clinic(patient_id, clinic_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        updates = payload.model_dump(exclude_unset=True)

        identity_changed = any(field in updates for field in ("first_name", "last_name", "birth_date", "mobile_number"))
        if identity_changed and not override_duplicate_warning:
            duplicates = await self.check_duplicates(
                clinic_id,
                first_name=updates.get("first_name", patient.first_name),
                last_name=updates.get("last_name", patient.last_name),
                birth_date=updates.get("birth_date", patient.birth_date),
                mobile_number=updates.get("mobile_number", patient.mobile_number),
                exclude_id=patient.id,
            )
            if duplicates:
                return PatientCreateResponse(patient=None, duplicates=duplicates)

        diff = _diff_fields(patient, updates)
        updates["updated_by"] = actor.id
        patient = await self.patient_repo.update(patient, **updates)

        await self.audit_service.log_event(
            clinic_id=clinic_id,
            user_id=actor.id,
            action="patient.updated",
            entity_type="patient",
            entity_id=str(patient_id),
            metadata={"fields": diff},
        )
        await self.session.commit()

        refreshed = await self.patient_repo.get_by_id_and_clinic(patient.id, clinic_id)
        read = PatientRead.model_validate(refreshed)
        await sync_queue_service.enqueue(
            entity_type="patient", record_id=refreshed.id, operation="update",
            payload=read.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return PatientCreateResponse(patient=read, duplicates=[])

    async def archive_patient(self, patient_id: UUID, *, clinic_id: UUID, actor: User) -> Patient:
        patient = await self.patient_repo.get_by_id_and_clinic(patient_id, clinic_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        patient.status = PatientStatus.ARCHIVED
        patient.updated_by = actor.id
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="patient.archived",
            entity_type="patient", entity_id=str(patient_id),
        )
        await self.session.commit()
        return await self.patient_repo.get_by_id_and_clinic(patient.id, clinic_id)

    async def restore_patient(self, patient_id: UUID, *, clinic_id: UUID, actor: User) -> Patient:
        patient = await self.patient_repo.get_by_id_and_clinic(patient_id, clinic_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        patient.status = PatientStatus.ACTIVE
        patient.updated_by = actor.id
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="patient.restored",
            entity_type="patient", entity_id=str(patient_id),
        )
        await self.session.commit()
        return await self.patient_repo.get_by_id_and_clinic(patient.id, clinic_id)

    async def search_patients(self, *, clinic_id: UUID, params: PatientSearchParams):
        return await self.patient_repo.search(clinic_id, params)

    async def get_qr(self, patient_id: UUID, *, clinic_id: UUID) -> tuple[UUID, str]:
        patient = await self.patient_repo.get_by_id_and_clinic(patient_id, clinic_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")
        if not patient.qr_code:
            patient.qr_code = _qr_payload(clinic_id, patient.id)
            await self.session.commit()
        return patient.id, patient.qr_code

    async def request_photo_upload_url(self, patient_id: UUID, *, clinic_id: UUID) -> dict:
        """Presigned-URL stub for Supabase Storage.

        TODO(storage): once a Supabase project/bucket is provisioned, replace
        this with a real call to the Supabase Storage API
        (`storage.from_(bucket).create_signed_upload_url(...)`) and return its
        real signed URL + token. Also TODO: generate a thumbnail (e.g. via a
        Supabase Storage transform or an async worker) once the original is
        uploaded, and store both `photo_url` and a `photo_thumbnail_url`.
        """
        patient = await self.patient_repo.get_by_id_and_clinic(patient_id, clinic_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

        token = secrets.token_urlsafe(24)
        object_path = f"clinics/{clinic_id}/patients/{patient_id}/photo-{token}.jpg"
        return {
            "upload_url": f"https://stub.supabase.local/storage/v1/upload/{object_path}",
            "public_url": f"https://stub.supabase.local/storage/v1/object/public/{object_path}",
            "expires_in": 600,
        }
