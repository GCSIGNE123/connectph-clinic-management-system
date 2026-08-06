"""Doctor Workspace endpoints (Phase 7).

The doctor's daily driver screen: today's assigned patients, quick visit
actions (call/recall/start/complete/no-show/cancel), and visit-open/lock
handshake for the read-focused visit viewer.

Role gating (see `core/dependencies.py`): Doctor role is scoped to their
own assigned visits (resolved via `User.doctor_id`); Owner/Administrator
may view/act on any doctor's visits (`doctor_id` query param selects
which); Receptionist gets view-only access.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_doctor_workspace_act_role,
    require_doctor_workspace_view_role,
)
from app.core.dependencies import DOCTOR_WORKSPACE_PRIVILEGED_ROLES
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.doctor_workspace import (
    CancelVisitRequest,
    DoctorDashboardResponse,
    DoctorQueueResponse,
    DoctorSessionStatus,
    LockInfo,
)
from app.schemas.visit import VisitDetail
from app.services.doctor_workspace_service import DoctorWorkspaceService

router = APIRouter(prefix="/doctor-workspace", tags=["doctor-workspace"])


def _is_privileged(user: User) -> bool:
    role_name = user.role.name if user.role is not None else None
    return role_name in DOCTOR_WORKSPACE_PRIVILEGED_ROLES


def _can_view_all(user: User) -> bool:
    """Owner/Administrator (privileged) AND Receptionist may view across all
    doctors (Receptionist is read-only per role gating, but still needs to
    see any doctor's queue for front-desk coordination)."""
    role_name = user.role.name if user.role is not None else None
    return _is_privileged(user) or role_name == "Receptionist"


async def _resolve_target_doctor(
    *, db: AsyncSession, clinic_id: UUID, current_user: User, doctor_id: UUID | None
) -> Doctor | None:
    """Resolves which Doctor's queue/dashboard/actions this request targets.

    - Doctor-role users are always scoped to their own linked Doctor record
      (the `doctor_id` query param is ignored for them).
    - Owner/Administrator may pass `doctor_id` to view a specific doctor's
      workspace, or omit it to see all doctors' visits (doctor=None).
    """
    privileged = _can_view_all(current_user)
    if not privileged:
        if current_user.doctor_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is not linked to a Doctor record.",
            )
        stmt = select(Doctor).where(
            Doctor.id == current_user.doctor_id, Doctor.clinic_id == clinic_id, Doctor.is_deleted.is_(False)
        ).options(selectinload(Doctor.branch), selectinload(Doctor.department))
        result = await db.execute(stmt)
        doctor = result.scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked doctor record not found")
        return doctor

    if doctor_id is None:
        return None
    stmt = select(Doctor).where(
        Doctor.id == doctor_id, Doctor.clinic_id == clinic_id, Doctor.is_deleted.is_(False)
    ).options(selectinload(Doctor.branch), selectinload(Doctor.department))
    result = await db.execute(stmt)
    doctor = result.scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
    return doctor


@router.get("/dashboard", response_model=DoctorDashboardResponse)
async def get_dashboard(
    doctor_id: UUID | None = Query(default=None, description="Administrator/Owner only: view a specific doctor's dashboard."),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_view_role),
) -> DoctorDashboardResponse:
    doctor = await _resolve_target_doctor(db=db, clinic_id=clinic_id, current_user=current_user, doctor_id=doctor_id)
    service = DoctorWorkspaceService(db)
    today = datetime.now(UTC).date()
    return await service.get_dashboard(clinic_id=clinic_id, doctor=doctor, visit_date=today)


@router.get("/queue", response_model=DoctorQueueResponse)
async def get_queue(
    doctor_id: UUID | None = Query(default=None, description="Administrator/Owner only: view a specific doctor's queue."),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_view_role),
) -> DoctorQueueResponse:
    doctor = await _resolve_target_doctor(db=db, clinic_id=clinic_id, current_user=current_user, doctor_id=doctor_id)
    service = DoctorWorkspaceService(db)
    today = datetime.now(UTC).date()
    return await service.get_queue(clinic_id=clinic_id, doctor=doctor, visit_date=today, current_user_id=current_user.id)


async def _act_doctor(db: AsyncSession, clinic_id: UUID, current_user: User) -> Doctor | None:
    """For act endpoints: Doctor role must resolve their own Doctor record;
    Owner/Administrator may act without one (the target visit's own
    `doctor_id` is used for activity-log attribution)."""
    if _is_privileged(current_user):
        if current_user.doctor_id is None:
            return None
        stmt = select(Doctor).where(Doctor.id == current_user.doctor_id, Doctor.clinic_id == clinic_id).options(
            selectinload(Doctor.branch), selectinload(Doctor.department)
        )
        return (await db.execute(stmt)).scalar_one_or_none()
    if current_user.doctor_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account is not linked to a Doctor record.")
    stmt = select(Doctor).where(Doctor.id == current_user.doctor_id, Doctor.clinic_id == clinic_id).options(
        selectinload(Doctor.branch), selectinload(Doctor.department)
    )
    doctor = (await db.execute(stmt)).scalar_one_or_none()
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked doctor record not found")
    return doctor


@router.post("/visits/{visit_id}/call", response_model=VisitDetail)
async def call_patient(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> VisitDetail:
    doctor = await _act_doctor(db, clinic_id, current_user)
    service = DoctorWorkspaceService(db)
    return await service.call_patient(visit_id, clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id, is_privileged=_is_privileged(current_user))


@router.post("/visits/{visit_id}/recall", response_model=VisitDetail)
async def recall_patient(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> VisitDetail:
    doctor = await _act_doctor(db, clinic_id, current_user)
    service = DoctorWorkspaceService(db)
    return await service.recall_patient(visit_id, clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id, is_privileged=_is_privileged(current_user))


@router.post("/visits/{visit_id}/start-consultation", response_model=VisitDetail)
async def start_consultation(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> VisitDetail:
    doctor = await _act_doctor(db, clinic_id, current_user)
    service = DoctorWorkspaceService(db)
    return await service.start_consultation(visit_id, clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id, is_privileged=_is_privileged(current_user))


@router.post("/visits/{visit_id}/complete-consultation", response_model=VisitDetail)
async def complete_consultation(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> VisitDetail:
    doctor = await _act_doctor(db, clinic_id, current_user)
    service = DoctorWorkspaceService(db)
    return await service.complete_consultation(visit_id, clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id, is_privileged=_is_privileged(current_user))


@router.post("/visits/{visit_id}/no-show", response_model=VisitDetail)
async def no_show(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> VisitDetail:
    doctor = await _act_doctor(db, clinic_id, current_user)
    service = DoctorWorkspaceService(db)
    return await service.mark_no_show(visit_id, clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id, is_privileged=_is_privileged(current_user))


@router.post("/visits/{visit_id}/cancel", response_model=VisitDetail)
async def cancel_visit(
    visit_id: UUID,
    payload: CancelVisitRequest,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> VisitDetail:
    doctor = await _act_doctor(db, clinic_id, current_user)
    service = DoctorWorkspaceService(db)
    return await service.cancel_visit(
        visit_id, clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id,
        is_privileged=_is_privileged(current_user), reason=payload.reason,
    )


@router.post("/visits/{visit_id}/open", response_model=LockInfo)
async def open_visit(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_view_role),
) -> LockInfo:
    doctor = await _act_doctor(db, clinic_id, current_user) if _is_privileged(current_user) or current_user.doctor_id else None
    service = DoctorWorkspaceService(db)
    is_privileged = _is_privileged(current_user)
    # Receptionist (view-only) may still "open" to view - but never gets
    # write access; treat as privileged=False with doctor=None so they can
    # only ever see lock info, never acquire it, unless already privileged.
    role_name = current_user.role.name if current_user.role is not None else None
    if role_name == "Receptionist":
        visit = await service._require_visit(visit_id, clinic_id)  # noqa: SLF001 - internal read-only peek
        lock = await service.repo.get_active_lock(visit_id, clinic_id)
        if lock is None:
            return LockInfo(locked=False)
        return LockInfo(
            locked=True, locked_by=lock.locked_by,
            locked_by_name=lock.locked_by_user.full_name if lock.locked_by_user else None,
            locked_at=lock.locked_at, is_self=False,
        )
    return await service.open_visit(visit_id, clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id, is_privileged=is_privileged)


@router.post("/visits/{visit_id}/release-lock", response_model=LockInfo)
async def release_lock(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_view_role),
) -> LockInfo:
    service = DoctorWorkspaceService(db)
    return await service.release_lock(visit_id, clinic_id=clinic_id, actor_id=current_user.id)


# --- Doctor Session Control (Client Acceptance Revisions Round 3, item 14) ---
# `doctor_id` query param lets Owner/Administrator act on a specific
# doctor's session, matching the existing `/dashboard` and `/queue`
# pattern above; a Doctor-role caller always acts on their own linked
# Doctor record and the query param is ignored for them (same as
# `_act_doctor`'s existing behaviour elsewhere in this file).

async def _session_target_doctor(db: AsyncSession, clinic_id: UUID, current_user: User, doctor_id: UUID | None) -> Doctor:
    if _is_privileged(current_user) and doctor_id is not None:
        stmt = select(Doctor).where(Doctor.id == doctor_id, Doctor.clinic_id == clinic_id)
        doctor = (await db.execute(stmt)).scalar_one_or_none()
        if doctor is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doctor not found")
        return doctor
    doctor = await _act_doctor(db, clinic_id, current_user)
    if doctor is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No doctor specified and this account is not linked to a Doctor record.")
    return doctor


@router.get("/session", response_model=DoctorSessionStatus)
async def get_session_status(
    doctor_id: UUID | None = Query(default=None),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_view_role),
) -> DoctorSessionStatus:
    doctor = await _session_target_doctor(db, clinic_id, current_user, doctor_id)
    service = DoctorWorkspaceService(db)
    return await service.get_session_status(clinic_id=clinic_id, doctor_id=doctor.id)


@router.post("/session/start", response_model=DoctorSessionStatus)
async def start_session(
    doctor_id: UUID | None = Query(default=None),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> DoctorSessionStatus:
    doctor = await _session_target_doctor(db, clinic_id, current_user, doctor_id)
    service = DoctorWorkspaceService(db)
    return await service.start_session(clinic_id=clinic_id, doctor_id=doctor.id, actor_id=current_user.id)


@router.post("/session/end", response_model=DoctorSessionStatus)
async def end_session(
    doctor_id: UUID | None = Query(default=None),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> DoctorSessionStatus:
    doctor = await _session_target_doctor(db, clinic_id, current_user, doctor_id)
    service = DoctorWorkspaceService(db)
    return await service.end_session(clinic_id=clinic_id, doctor_id=doctor.id, actor_id=current_user.id)


@router.post("/next-patient", response_model=VisitDetail | None)
async def next_patient(
    doctor_id: UUID | None = Query(default=None),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_doctor_workspace_act_role),
) -> VisitDetail | None:
    """Completes/moves past whichever visit is currently Called or
    InConsultation for this doctor (if any), then calls the earliest
    Waiting visit for this doctor. Returns null if there's nothing waiting."""
    doctor = await _session_target_doctor(db, clinic_id, current_user, doctor_id)
    service = DoctorWorkspaceService(db)
    today = datetime.now(UTC).date()
    return await service.next_patient(clinic_id=clinic_id, doctor=doctor, actor_id=current_user.id, visit_date=today)
