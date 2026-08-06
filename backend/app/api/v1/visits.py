"""Visit (encounter) endpoints: list/search/detail/timeline/update/status,
tenant-scoped and role-gated. `POST /visits` exists for internal/test use -
the real-world trigger for visit creation is `POST /queues` (see
`services/queue_service.py`). See `core/dependencies.py`
(`VISIT_*_ROLES`) for the exact role matrix.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_visit_close_role,
    require_visit_create_role,
    require_visit_modify_role,
    require_visit_view_role,
)
from app.models.user import User
from app.models.visit import VisitStatus, VisitType
from app.schemas.visit import (
    VisitCreate,
    VisitDetail,
    VisitListResponse,
    VisitPreQueueCreate,
    VisitStatusUpdate,
    VisitTimelineEventRead,
    VisitUpdate,
)
from app.services.visit_service import VisitService

router = APIRouter(prefix="/visits", tags=["visits"])


@router.get("", response_model=VisitListResponse)
async def list_visits(
    q: str | None = Query(default=None, description="Search visit number, queue number, or patient name/number."),
    branch_id: UUID | None = Query(default=None),
    patient_id: UUID | None = Query(default=None),
    doctor_id: UUID | None = Query(default=None),
    department_id: UUID | None = Query(default=None),
    status_filter: VisitStatus | None = Query(default=None, alias="status"),
    visit_type: VisitType | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_visit_view_role),
) -> VisitListResponse:
    from app.schemas.visit import VisitSearchParams

    params = VisitSearchParams(
        q=q, branch_id=branch_id, patient_id=patient_id, doctor_id=doctor_id, department_id=department_id,
        status=status_filter, visit_type=visit_type, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    service = VisitService(db)
    items, total = await service.search(clinic_id=clinic_id, params=params)
    return VisitListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{visit_id}", response_model=VisitDetail)
async def get_visit(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_visit_view_role),
) -> VisitDetail:
    service = VisitService(db)
    return await service.get_detail(visit_id, clinic_id=clinic_id)


@router.get("/{visit_id}/timeline", response_model=list[VisitTimelineEventRead])
async def get_visit_timeline(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(require_visit_view_role),
) -> list[VisitTimelineEventRead]:
    service = VisitService(db)
    return await service.get_timeline(visit_id, clinic_id=clinic_id)


@router.post("", response_model=VisitDetail, status_code=status.HTTP_201_CREATED)
async def create_visit(
    payload: VisitCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_visit_create_role),
) -> VisitDetail:
    """Direct visit creation for internal/test use. Real-world receptionist
    workflow triggers visit creation via `POST /queues` instead."""
    service = VisitService(db)
    return await service.create_visit(payload, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/pre-queue", response_model=VisitDetail, status_code=status.HTTP_201_CREATED)
async def create_pre_queue_visit(
    payload: VisitPreQueueCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_visit_create_role),
) -> VisitDetail:
    """Phase 21 (Vitals-before-Queue): Reception calls this to create a
    `DraftVitals` Visit for a Consultation/Follow-up service BEFORE a Queue
    ticket exists, so vitals can be entered first via the existing
    `POST /visits/{visit_id}/consultation/open-for-reception` +
    `PUT /consultations/{id}/soap/subjective-objective` endpoints (reused
    unmodified). `POST /queues` later attaches a Queue ticket to this same
    draft Visit (see `services/queue_service.py::create_queue`)."""
    service = VisitService(db)
    return await service.create_draft_visit_for_pre_queue(payload, clinic_id=clinic_id, actor_id=current_user.id)


@router.patch("/{visit_id}", response_model=VisitDetail)
async def update_visit(
    visit_id: UUID,
    payload: VisitUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_visit_modify_role),
) -> VisitDetail:
    service = VisitService(db)
    return await service.update_visit(visit_id, payload, clinic_id=clinic_id, actor_id=current_user.id)


@router.patch("/{visit_id}/status", response_model=VisitDetail)
async def update_visit_status(
    visit_id: UUID,
    payload: VisitStatusUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_visit_close_role),
) -> VisitDetail:
    service = VisitService(db)
    return await service.change_status(
        visit_id, clinic_id=clinic_id, actor_id=current_user.id, new_status=payload.status, note=payload.note
    )
