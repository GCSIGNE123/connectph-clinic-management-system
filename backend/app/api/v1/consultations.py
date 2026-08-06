"""Clinical Consultation / SOAP endpoints (Phase 8).

Role gating (see `core/dependencies.py`): only the visit's assigned doctor
(`current_user.doctor_id == visit.doctor_id`) may edit SOAP/diagnosis/
attachments; Administrator/Owner may view only (read-only, stricter than
Phase 7); Receptionist is excluded entirely - gets 403 on both view and
edit, enforced by simply never including Receptionist in
`require_consultation_view_role`'s allowed set.
"""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import (
    CONSULTATION_PRIVILEGED_ROLES,
    get_db,
    require_clinic_context,
    require_consultation_edit_role,
    require_consultation_view_role,
    require_soap_subjective_objective_role,
)
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.consultation import (
    AttachmentUploadRequest,
    AttachmentUploadResponse,
    ConsultationCompleteRequest,
    ConsultationDetail,
    ConsultationTimelineResponse,
    DiagnosisCreate,
    DiagnosisRead,
    DiagnosisUpdate,
    SoapNoteSubjectiveObjectiveRead,
    SoapNoteSubjectiveObjectiveUpsert,
    SoapNoteUpsert,
)
from app.services.consultation_service import ConsultationService

router = APIRouter(tags=["consultations"])


def _is_privileged(user: User) -> bool:
    role_name = user.role.name if user.role is not None else None
    return role_name in CONSULTATION_PRIVILEGED_ROLES


async def _require_visit_and_permissions(db: AsyncSession, clinic_id: UUID, current_user: User, visit_id: UUID):
    """Resolves the visit and whether the current user may edit it.

    Only the assigned doctor may edit; Owner/Administrator may view any
    visit's consultation but never edit (per spec, stricter than Phase 7).
    """
    from app.repositories.visit_repository import VisitRepository

    visit = await VisitRepository(db).get_by_id_and_clinic(visit_id, clinic_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

    privileged = _is_privileged(current_user)
    can_edit = (not privileged) and current_user.doctor_id is not None and current_user.doctor_id == visit.doctor_id
    if not privileged and current_user.doctor_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not linked to a Doctor record.")
    if not privileged and current_user.doctor_id != visit.doctor_id:
        # Doctor role but not the assigned doctor - view-only, same as a
        # privileged viewer, not a 403 (spec: other doctors may see the
        # visit exists via Doctor Workspace, but not edit this consultation).
        can_edit = False
    return visit, can_edit


async def _resolve_doctor_id(db: AsyncSession, clinic_id: UUID, current_user: User, visit) -> UUID:
    """Doctor id to attribute a *newly created* Consultation to - the visit's
    assigned doctor if set, otherwise the current user's own linked doctor."""
    if visit.doctor_id is not None:
        return visit.doctor_id
    if current_user.doctor_id is not None:
        return current_user.doctor_id
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Visit has no assigned doctor.")


async def _get_consultation_and_permissions(db: AsyncSession, clinic_id: UUID, current_user: User, consultation_id: UUID):
    from app.repositories.consultation_repository import ConsultationRepository

    consultation = await ConsultationRepository(db).get_by_id(consultation_id, clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    _, can_edit = await _require_visit_and_permissions(db, clinic_id, current_user, consultation.visit_id)
    return consultation, can_edit


@router.post("/visits/{visit_id}/consultation/open", response_model=ConsultationDetail)
async def open_consultation(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_view_role),
) -> ConsultationDetail:
    visit, can_edit = await _require_visit_and_permissions(db, clinic_id, current_user, visit_id)
    doctor_id = await _resolve_doctor_id(db, clinic_id, current_user, visit)
    service = ConsultationService(db)
    return await service.open_consultation(
        visit_id, clinic_id=clinic_id, doctor_id=doctor_id, actor_id=current_user.id,
        current_user_id=current_user.id, acquire_lock=can_edit,
    )


@router.get("/visits/{visit_id}/consultation", response_model=ConsultationDetail | None)
async def get_consultation_for_visit(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_view_role),
) -> ConsultationDetail | None:
    await _require_visit_and_permissions(db, clinic_id, current_user, visit_id)
    service = ConsultationService(db)
    return await service.get_consultation_for_visit(visit_id, clinic_id=clinic_id, current_user_id=current_user.id)


@router.get("/consultations/{consultation_id}", response_model=ConsultationDetail)
async def get_consultation(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_view_role),
) -> ConsultationDetail:
    await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    return await service.get_detail(consultation_id, clinic_id=clinic_id, current_user_id=current_user.id)


@router.post("/visits/{visit_id}/consultation/open-for-reception", response_model=ConsultationDetail)
async def open_consultation_for_reception(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_soap_subjective_objective_role),
) -> ConsultationDetail:
    """Phase 20 (items 4-5): Receptionist/Nurse entry point to open (or
    resume) a visit's consultation for the sole purpose of entering
    Subjective/Objective data - never acquires the edit lock, so it never
    blocks the assigned Doctor from opening the same visit normally via
    `POST /visits/{id}/consultation/open`."""
    service = ConsultationService(db)
    return await service.open_consultation_for_reception(
        visit_id, clinic_id=clinic_id, actor_id=current_user.id, current_user_id=current_user.id,
    )


@router.get("/consultations/{consultation_id}/soap/subjective-objective", response_model=SoapNoteSubjectiveObjectiveRead | None)
async def get_soap_subjective_objective(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_soap_subjective_objective_role),
):
    """Phase 20 (items 4-5): field-restricted read for Receptionist/Nurse -
    returns ONLY Subjective/Objective fields (never Assessment/Plan), unlike
    the full `GET /consultations/{id}/soap` which stays Doctor/Owner/
    Administrator-only via `require_consultation_view_role`."""
    from app.repositories.consultation_repository import ConsultationRepository

    consultation = await ConsultationRepository(db).get_by_id(consultation_id, clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    note = await ConsultationRepository(db).get_soap(consultation_id, clinic_id)
    return SoapNoteSubjectiveObjectiveRead.model_validate(note) if note else None


@router.put("/consultations/{consultation_id}/soap/subjective-objective", response_model=ConsultationDetail)
async def save_soap_subjective_objective(
    consultation_id: UUID,
    payload: SoapNoteSubjectiveObjectiveUpsert,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_soap_subjective_objective_role),
) -> ConsultationDetail:
    """Phase 20 (items 4-5): Receptionist/Nurse (and Doctor/Owner/
    Administrator) may write ONLY Subjective/Objective fields here -
    Assessment/Plan remain reachable only via `PUT /consultations/{id}/soap`
    (`require_consultation_edit_role`, Doctor/Owner/Administrator only, and
    Owner/Administrator never get `can_edit=True` there either)."""
    from app.repositories.consultation_repository import ConsultationRepository

    consultation = await ConsultationRepository(db).get_by_id(consultation_id, clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")
    service = ConsultationService(db)
    return await service.save_soap_subjective_objective(
        consultation_id, payload.model_dump(exclude_unset=True), clinic_id=clinic_id,
        actor_id=current_user.id, current_user_id=current_user.id,
    )


@router.get("/consultations/{consultation_id}/soap")
async def get_soap(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_view_role),
):
    await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    from app.repositories.consultation_repository import ConsultationRepository
    from app.schemas.consultation import SoapNoteRead

    note = await ConsultationRepository(db).get_soap(consultation_id, clinic_id)
    return SoapNoteRead.model_validate(note) if note else None


@router.put("/consultations/{consultation_id}/soap", response_model=ConsultationDetail)
async def save_soap(
    consultation_id: UUID,
    payload: SoapNoteUpsert,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_edit_role),
) -> ConsultationDetail:
    _, can_edit = await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    return await service.save_soap(
        consultation_id, payload.model_dump(exclude_unset=True), clinic_id=clinic_id, actor_id=current_user.id,
        current_user_id=current_user.id, can_edit=can_edit,
    )


@router.post("/consultations/{consultation_id}/diagnoses", response_model=ConsultationDetail)
async def add_diagnosis(
    consultation_id: UUID,
    payload: DiagnosisCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_edit_role),
) -> ConsultationDetail:
    _, can_edit = await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    return await service.add_diagnosis(
        consultation_id, payload.model_dump(), clinic_id=clinic_id, actor_id=current_user.id,
        current_user_id=current_user.id, can_edit=can_edit,
    )


@router.get("/consultations/{consultation_id}/diagnoses", response_model=list[DiagnosisRead])
async def list_diagnoses(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_view_role),
) -> list[DiagnosisRead]:
    await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    return await service.list_diagnoses(consultation_id, clinic_id=clinic_id)


@router.patch("/consultations/{consultation_id}/diagnoses/{diagnosis_id}", response_model=ConsultationDetail)
async def update_diagnosis(
    consultation_id: UUID,
    diagnosis_id: UUID,
    payload: DiagnosisUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_edit_role),
) -> ConsultationDetail:
    _, can_edit = await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    return await service.update_diagnosis(
        consultation_id, diagnosis_id, payload.model_dump(exclude_unset=True), clinic_id=clinic_id,
        actor_id=current_user.id, current_user_id=current_user.id, can_edit=can_edit,
    )


@router.post("/consultations/{consultation_id}/complete", response_model=ConsultationDetail)
async def complete_consultation(
    consultation_id: UUID,
    payload: ConsultationCompleteRequest | None = Body(default=None),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_edit_role),
) -> ConsultationDetail:
    _, can_edit = await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    fee = payload.consultation_fee if payload is not None else None
    return await service.complete_consultation(
        consultation_id, clinic_id=clinic_id, actor_id=current_user.id, current_user_id=current_user.id,
        can_edit=can_edit, consultation_fee=fee,
    )


@router.post("/consultations/{consultation_id}/sign", response_model=ConsultationDetail)
async def sign_consultation(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_edit_role),
) -> ConsultationDetail:
    _, can_edit = await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    return await service.sign_consultation(
        consultation_id, clinic_id=clinic_id, actor_id=current_user.id, current_user_id=current_user.id, can_edit=can_edit,
    )


@router.post("/consultations/{consultation_id}/attachments", response_model=AttachmentUploadResponse)
async def upload_attachment(
    consultation_id: UUID,
    payload: AttachmentUploadRequest,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_edit_role),
) -> AttachmentUploadResponse:
    _, can_edit = await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    result = await service.request_attachment_upload(
        consultation_id, clinic_id=clinic_id, actor_id=current_user.id, file_name=payload.file_name,
        attachment_type=payload.attachment_type, file_size_bytes=payload.file_size_bytes, can_edit=can_edit,
    )
    return AttachmentUploadResponse(**result)


@router.get("/consultations/{consultation_id}/attachments")
async def list_attachments(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_view_role),
):
    await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    return await service.list_attachments(consultation_id, clinic_id=clinic_id)


@router.get("/consultations/{consultation_id}/timeline", response_model=ConsultationTimelineResponse)
async def get_timeline(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_consultation_view_role),
) -> ConsultationTimelineResponse:
    await _get_consultation_and_permissions(db, clinic_id, current_user, consultation_id)
    service = ConsultationService(db)
    visit_id, events = await service.get_timeline(consultation_id, clinic_id=clinic_id)
    return ConsultationTimelineResponse(visit_id=visit_id, events=events)
