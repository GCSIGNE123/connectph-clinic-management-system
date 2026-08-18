"""Medical Certificate service.

Lifecycle: `Draft -> Issued -> Cancelled`.

- `create_draft`/`update_draft`: freely editable, not a legal document yet.
- `issue`: the ONLY place a `certificate_number` is assigned (via
  `MedicalCertificateNumberGenerator`) and `issued_at` is stamped. From this
  point on the row is immutable - `update_draft` explicitly refuses to touch
  a non-Draft certificate.
- `cancel`: requires a reason; sets `cancelled_at`/`cancelled_reason`/
  `cancelled_by`. The cancelled row is never deleted and remains fully
  visible in every list/history endpoint - only its `status` changes.
- `reissue` (cancel + issue in one call): the correction workflow - cancels
  the original (reason required) and creates a brand-new Draft-then-Issued
  certificate pre-filled from the original's content, linking the OLD row's
  `superseded_by_id` to the NEW row's id. The new certificate gets its own
  fresh `certificate_number`.

Authorization mirrors `ClinicalOrdersService._require_can_edit` /
`api/v1/clinical_orders.py::_permissions_for_consultation` exactly: only the
consultation's assigned doctor may create/edit/issue/cancel; Owner/
Administrator/Receptionist/Cashier pass the broader role gate for read/print
endpoints but are never granted `can_edit=True` (enforced by the caller,
`api/v1/medical_certificates.py`, and re-checked here via `_require_can_edit`
as defense in depth - never trust the frontend to have hidden the button).
"""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic import Clinic
from app.models.doctor import Doctor
from app.models.medical_certificate import MedicalCertificate, MedicalCertificateStatus, MedicalCertificateType
from app.models.visit import VisitTimelineEventType
from app.repositories.consultation_repository import ConsultationRepository
from app.repositories.medical_certificate_repository import MedicalCertificateRepository
from app.repositories.visit_repository import VisitRepository
from app.schemas.medical_certificate import MedicalCertificateCreate, MedicalCertificateDetail, MedicalCertificateUpdate
from app.services.audit_service import AuditService
from app.services.clinical_number_generator import MedicalCertificateNumberGenerator


def _full_name(entity) -> str:
    parts = [entity.first_name, getattr(entity, "middle_name", None), entity.last_name, getattr(entity, "suffix", None)]
    return " ".join(p for p in parts if p)


def _age_years(birth_date: date, *, as_of: date) -> int:
    years = as_of.year - birth_date.year
    if (as_of.month, as_of.day) < (birth_date.month, birth_date.day):
        years -= 1
    return years


class MedicalCertificateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MedicalCertificateRepository(session)
        self.consultation_repo = ConsultationRepository(session)
        self.visit_repo = VisitRepository(session)
        self.audit_service = AuditService(session)

    # --- Internal helpers ---

    def _require_can_edit(self, can_edit: bool) -> None:
        if not can_edit:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have edit access to this consultation.")

    async def _require_consultation(self, consultation_id: UUID, clinic_id: UUID):
        consultation = await self.consultation_repo.get_by_id(consultation_id, clinic_id)
        if consultation is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
        return consultation

    async def _require_certificate(self, certificate_id: UUID, clinic_id: UUID) -> MedicalCertificate:
        certificate = await self.repo.get(certificate_id, clinic_id)
        if certificate is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medical certificate not found")
        return certificate

    async def _to_detail(self, certificate: MedicalCertificate, *, clinic_id: UUID) -> MedicalCertificateDetail:
        base = MedicalCertificateDetail.model_validate(certificate)
        patient = certificate.patient
        doctor = certificate.doctor
        clinic = await self.session.get(Clinic, clinic_id)
        visit = await self.visit_repo.get_by_id_and_clinic(certificate.visit_id, clinic_id)

        base.patient_name = patient.full_name if patient else None
        base.patient_age = _age_years(patient.birth_date, as_of=date.today()) if patient else None
        base.patient_sex = patient.gender.value if patient and patient.gender else None
        base.doctor_name = _full_name(doctor) if doctor else None
        base.doctor_prc_license = doctor.prc_license if doctor else None
        base.doctor_ptr_number = doctor.ptr_number if doctor else None
        base.clinic_name = clinic.name if clinic else None
        base.clinic_logo_url = clinic.logo_url if clinic else None
        base.clinic_address = ", ".join(filter(None, [clinic.address, clinic.city, clinic.province])) if clinic else None
        base.clinic_license_number = clinic.license_number if clinic else None
        base.visit_number = visit.visit_number if visit else None
        return base

    # --- Draft ---

    async def create_draft(
        self, consultation_id: UUID, payload: MedicalCertificateCreate, *, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> MedicalCertificateDetail:
        self._require_can_edit(can_edit)
        consultation = await self._require_consultation(consultation_id, clinic_id)

        certificate = await self.repo.create(
            clinic_id=clinic_id, consultation_id=consultation_id, visit_id=consultation.visit_id,
            branch_id=consultation.branch_id, patient_id=consultation.patient_id, doctor_id=consultation.doctor_id,
            certificate_type=payload.certificate_type, status=MedicalCertificateStatus.DRAFT,
            findings=payload.findings, recommendation=payload.recommendation, rest_days=payload.rest_days,
            date_from=payload.date_from, date_to=payload.date_to, notes=payload.notes,
            created_by=actor_id, updated_by=actor_id,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="medical_certificate.draft_created",
            entity_type="medical_certificate", entity_id=str(certificate.id),
            metadata={"certificate_type": payload.certificate_type.value},
        )
        await self.session.commit()
        return await self._to_detail(certificate, clinic_id=clinic_id)

    async def update_draft(
        self, certificate_id: UUID, payload: MedicalCertificateUpdate, *, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> MedicalCertificateDetail:
        self._require_can_edit(can_edit)
        certificate = await self._require_certificate(certificate_id, clinic_id)
        if certificate.status != MedicalCertificateStatus.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot edit a certificate that is already {certificate.status.value}. "
                       "Issued certificates are immutable - cancel and reissue instead.",
            )
        updates = payload.model_dump(exclude_unset=True)
        updates["updated_by"] = actor_id
        certificate = await self.repo.update(certificate, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="medical_certificate.draft_updated",
            entity_type="medical_certificate", entity_id=str(certificate.id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self._to_detail(certificate, clinic_id=clinic_id)

    # --- Issue ---

    async def issue(self, certificate_id: UUID, *, clinic_id: UUID, actor_id: UUID, can_edit: bool) -> MedicalCertificateDetail:
        self._require_can_edit(can_edit)
        certificate = await self._require_certificate(certificate_id, clinic_id)
        if certificate.status != MedicalCertificateStatus.DRAFT:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot issue a certificate that is already {certificate.status.value}.",
            )

        generator = MedicalCertificateNumberGenerator(self.session)
        certificate_number = await generator.next_number(clinic_id)
        now = datetime.now(UTC)

        # Doctor E-Signature: snapshot the doctor's CURRENT signature at
        # the moment of issuance - a deliberate exception to this
        # certificate's otherwise-live-joined doctor fields (see the model
        # docstring and migration 0036). No fabricated signature: a doctor
        # with none configured simply issues with a blank signature area.
        doctor = await self.session.get(Doctor, certificate.doctor_id)
        signature_snapshot = doctor.signature_url if doctor is not None else None

        certificate = await self.repo.update(
            certificate, status=MedicalCertificateStatus.ISSUED, certificate_number=certificate_number,
            issued_at=now, updated_by=actor_id, doctor_signature_snapshot_url=signature_snapshot,
        )

        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=certificate.visit_id, event_type=VisitTimelineEventType.CERTIFICATE_ISSUED,
            occurred_at=now, recorded_by=actor_id,
            note=f"Medical certificate issued ({certificate.certificate_type.value}) - {certificate_number}",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="medical_certificate.issued",
            entity_type="medical_certificate", entity_id=str(certificate.id),
            metadata={"certificate_number": certificate_number, "certificate_type": certificate.certificate_type.value},
        )
        await self.session.commit()
        return await self._to_detail(certificate, clinic_id=clinic_id)

    # --- Cancel ---

    async def cancel(
        self, certificate_id: UUID, *, reason: str, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> MedicalCertificateDetail:
        self._require_can_edit(can_edit)
        certificate = await self._require_certificate(certificate_id, clinic_id)
        if certificate.status != MedicalCertificateStatus.ISSUED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only an Issued certificate can be cancelled (current status: {certificate.status.value}).",
            )
        now = datetime.now(UTC)
        certificate = await self.repo.update(
            certificate, status=MedicalCertificateStatus.CANCELLED, cancelled_at=now,
            cancelled_reason=reason, cancelled_by=actor_id, updated_by=actor_id,
        )
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=certificate.visit_id, event_type=VisitTimelineEventType.CERTIFICATE_CANCELLED,
            occurred_at=now, recorded_by=actor_id,
            note=f"Medical certificate cancelled - {certificate.certificate_number} ({reason})",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="medical_certificate.cancelled",
            entity_type="medical_certificate", entity_id=str(certificate.id),
            metadata={"certificate_number": certificate.certificate_number, "reason": reason},
        )
        await self.session.commit()
        return await self._to_detail(certificate, clinic_id=clinic_id)

    async def reissue(
        self, certificate_id: UUID, *, reason: str, clinic_id: UUID, actor_id: UUID, can_edit: bool
    ) -> MedicalCertificateDetail:
        """Cancel + Issue New, in one call - the only supported way to
        correct an already-issued certificate. Never mutates the original's
        content; it only flips status and links `superseded_by_id`."""
        self._require_can_edit(can_edit)
        original = await self._require_certificate(certificate_id, clinic_id)
        if original.status != MedicalCertificateStatus.ISSUED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Only an Issued certificate can be reissued (current status: {original.status.value}).",
            )

        new_certificate = await self.repo.create(
            clinic_id=clinic_id, consultation_id=original.consultation_id, visit_id=original.visit_id,
            branch_id=original.branch_id, patient_id=original.patient_id, doctor_id=original.doctor_id,
            certificate_type=original.certificate_type, status=MedicalCertificateStatus.DRAFT,
            findings=original.findings, recommendation=original.recommendation, rest_days=original.rest_days,
            date_from=original.date_from, date_to=original.date_to, notes=original.notes,
            created_by=actor_id, updated_by=actor_id,
        )
        generator = MedicalCertificateNumberGenerator(self.session)
        certificate_number = await generator.next_number(clinic_id)
        now = datetime.now(UTC)
        doctor = await self.session.get(Doctor, new_certificate.doctor_id)
        signature_snapshot = doctor.signature_url if doctor is not None else None
        new_certificate = await self.repo.update(
            new_certificate, status=MedicalCertificateStatus.ISSUED, certificate_number=certificate_number,
            issued_at=now, updated_by=actor_id, doctor_signature_snapshot_url=signature_snapshot,
        )

        original = await self.repo.update(
            original, status=MedicalCertificateStatus.CANCELLED, cancelled_at=now,
            cancelled_reason=reason, cancelled_by=actor_id, updated_by=actor_id,
            superseded_by_id=new_certificate.id,
        )

        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=original.visit_id, event_type=VisitTimelineEventType.CERTIFICATE_CANCELLED,
            occurred_at=now, recorded_by=actor_id,
            note=f"Medical certificate cancelled - {original.certificate_number} ({reason}); superseded by {certificate_number}",
        )
        await self.visit_repo.add_timeline_event(
            clinic_id=clinic_id, visit_id=new_certificate.visit_id, event_type=VisitTimelineEventType.CERTIFICATE_ISSUED,
            occurred_at=now, recorded_by=actor_id,
            note=f"Medical certificate issued ({new_certificate.certificate_type.value}) - {certificate_number} "
                 f"(supersedes {original.certificate_number})",
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="medical_certificate.cancelled",
            entity_type="medical_certificate", entity_id=str(original.id),
            metadata={"certificate_number": original.certificate_number, "reason": reason, "superseded_by": str(new_certificate.id)},
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="medical_certificate.issued",
            entity_type="medical_certificate", entity_id=str(new_certificate.id),
            metadata={"certificate_number": certificate_number, "supersedes": str(original.id)},
        )
        await self.session.commit()
        return await self._to_detail(new_certificate, clinic_id=clinic_id)

    # --- Print ---

    async def record_print(self, certificate_id: UUID, *, clinic_id: UUID, actor_id: UUID) -> None:
        certificate = await self._require_certificate(certificate_id, clinic_id)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor_id, action="medical_certificate.printed",
            entity_type="medical_certificate", entity_id=str(certificate.id),
            metadata={"certificate_number": certificate.certificate_number, "status": certificate.status.value},
        )
        await self.session.commit()

    # --- Reads ---

    async def get(self, certificate_id: UUID, *, clinic_id: UUID) -> MedicalCertificateDetail:
        certificate = await self._require_certificate(certificate_id, clinic_id)
        return await self._to_detail(certificate, clinic_id=clinic_id)

    async def list_for_consultation(self, consultation_id: UUID, *, clinic_id: UUID) -> list[MedicalCertificateDetail]:
        await self._require_consultation(consultation_id, clinic_id)
        rows = await self.repo.list_for_consultation(consultation_id, clinic_id)
        return [await self._to_detail(r, clinic_id=clinic_id) for r in rows]

    async def list_for_visit(self, visit_id: UUID, *, clinic_id: UUID) -> list[MedicalCertificateDetail]:
        rows = await self.repo.list_for_visit(visit_id, clinic_id)
        return [await self._to_detail(r, clinic_id=clinic_id) for r in rows]

    async def list_for_patient(self, patient_id: UUID, *, clinic_id: UUID) -> list[MedicalCertificateDetail]:
        rows = await self.repo.list_for_patient(patient_id, clinic_id)
        return [await self._to_detail(r, clinic_id=clinic_id) for r in rows]
