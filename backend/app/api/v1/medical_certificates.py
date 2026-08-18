"""Medical Certificate endpoints.

Role gating mirrors `api/v1/clinical_orders.py` exactly: only the visit's
assigned doctor may create/edit/issue/cancel/reissue; Owner/Administrator
pass the broader role gate but are view/print-only (never granted
`can_edit=True`, per product decision - Owner/Admin must NOT issue on a
doctor's behalf in v1); Receptionist/Cashier are view+reprint only.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    MEDICAL_CERTIFICATE_PRIVILEGED_ROLES,
    get_db,
    require_clinic_context,
    require_medical_certificate_edit_role,
    require_medical_certificate_view_role,
)
from app.models.user import User
from app.repositories.visit_repository import VisitRepository
from app.schemas.medical_certificate import (
    MedicalCertificateCancel,
    MedicalCertificateCreate,
    MedicalCertificateDetail,
    MedicalCertificateUpdate,
)
from app.services.medical_certificate_service import MedicalCertificateService

router = APIRouter(tags=["medical-certificates"])


def _is_privileged(user: User) -> bool:
    role_name = user.role.name if user.role is not None else None
    return role_name in MEDICAL_CERTIFICATE_PRIVILEGED_ROLES


async def _permissions_for_consultation(db: AsyncSession, clinic_id: UUID, current_user: User, consultation_id: UUID) -> bool:
    """Resolves whether the current user may edit (create/update/issue/
    cancel) medical certificates for this consultation - mirrors
    `api/v1/clinical_orders.py::_permissions_for_consultation` exactly."""
    from app.repositories.consultation_repository import ConsultationRepository

    consultation = await ConsultationRepository(db).get_by_id(consultation_id, clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    visit = await VisitRepository(db).get_by_id_and_clinic(consultation.visit_id, clinic_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

    if _is_privileged(current_user):
        return False  # view-only, per product decision
    role_name = current_user.role.name if current_user.role is not None else None
    if role_name in ("Receptionist", "Cashier"):
        return False  # view + reprint only
    can_edit = current_user.doctor_id is not None and current_user.doctor_id == visit.doctor_id
    return can_edit


async def _permissions_for_certificate(db: AsyncSession, clinic_id: UUID, current_user: User, certificate_id: UUID) -> bool:
    from app.repositories.medical_certificate_repository import MedicalCertificateRepository

    certificate = await MedicalCertificateRepository(db).get(certificate_id, clinic_id)
    if certificate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medical certificate not found")
    return await _permissions_for_consultation(db, clinic_id, current_user, certificate.consultation_id)


@router.post("/consultations/{consultation_id}/medical-certificates", response_model=MedicalCertificateDetail)
async def create_medical_certificate_draft(
    consultation_id: UUID,
    payload: MedicalCertificateCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_edit_role),
) -> MedicalCertificateDetail:
    can_edit = await _permissions_for_consultation(db, clinic_id, current_user, consultation_id)
    service = MedicalCertificateService(db)
    return await service.create_draft(consultation_id, payload, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.get("/consultations/{consultation_id}/medical-certificates", response_model=list[MedicalCertificateDetail])
async def list_medical_certificates_for_consultation(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_view_role),
) -> list[MedicalCertificateDetail]:
    service = MedicalCertificateService(db)
    return await service.list_for_consultation(consultation_id, clinic_id=clinic_id)


@router.get("/visits/{visit_id}/medical-certificates", response_model=list[MedicalCertificateDetail])
async def list_medical_certificates_for_visit(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_view_role),
) -> list[MedicalCertificateDetail]:
    service = MedicalCertificateService(db)
    return await service.list_for_visit(visit_id, clinic_id=clinic_id)


@router.get("/patients/{patient_id}/medical-certificates", response_model=list[MedicalCertificateDetail])
async def list_medical_certificates_for_patient(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_view_role),
) -> list[MedicalCertificateDetail]:
    service = MedicalCertificateService(db)
    return await service.list_for_patient(patient_id, clinic_id=clinic_id)


@router.get("/medical-certificates/{certificate_id}", response_model=MedicalCertificateDetail)
async def get_medical_certificate(
    certificate_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_view_role),
) -> MedicalCertificateDetail:
    service = MedicalCertificateService(db)
    return await service.get(certificate_id, clinic_id=clinic_id)


@router.patch("/medical-certificates/{certificate_id}", response_model=MedicalCertificateDetail)
async def update_medical_certificate_draft(
    certificate_id: UUID,
    payload: MedicalCertificateUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_edit_role),
) -> MedicalCertificateDetail:
    can_edit = await _permissions_for_certificate(db, clinic_id, current_user, certificate_id)
    service = MedicalCertificateService(db)
    return await service.update_draft(certificate_id, payload, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.post("/medical-certificates/{certificate_id}/issue", response_model=MedicalCertificateDetail)
async def issue_medical_certificate(
    certificate_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_edit_role),
) -> MedicalCertificateDetail:
    can_edit = await _permissions_for_certificate(db, clinic_id, current_user, certificate_id)
    service = MedicalCertificateService(db)
    return await service.issue(certificate_id, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.post("/medical-certificates/{certificate_id}/cancel", response_model=MedicalCertificateDetail)
async def cancel_medical_certificate(
    certificate_id: UUID,
    payload: MedicalCertificateCancel,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_edit_role),
) -> MedicalCertificateDetail:
    can_edit = await _permissions_for_certificate(db, clinic_id, current_user, certificate_id)
    service = MedicalCertificateService(db)
    return await service.cancel(certificate_id, reason=payload.reason, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.post("/medical-certificates/{certificate_id}/reissue", response_model=MedicalCertificateDetail)
async def reissue_medical_certificate(
    certificate_id: UUID,
    payload: MedicalCertificateCancel,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_edit_role),
) -> MedicalCertificateDetail:
    can_edit = await _permissions_for_certificate(db, clinic_id, current_user, certificate_id)
    service = MedicalCertificateService(db)
    return await service.reissue(certificate_id, reason=payload.reason, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.post("/medical-certificates/{certificate_id}/print", response_model=None)
async def print_medical_certificate(
    certificate_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_medical_certificate_view_role),
) -> dict:
    service = MedicalCertificateService(db)
    await service.record_print(certificate_id, clinic_id=clinic_id, actor_id=current_user.id)
    return {"status": "ok"}
