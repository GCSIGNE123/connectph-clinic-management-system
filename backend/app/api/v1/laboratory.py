"""Laboratory Management endpoints (Phase 10).

Role gating (see `core/dependencies.py`): Doctor still creates Laboratory-
category orders via the unchanged Phase 9 `/consultations/{id}/orders`
endpoint; Laboratory personnel (plus Owner/Administrator) collect/process/
enter-results/release/cancel/attach here; Reception is read-only; Doctor is
read-only on this module's endpoints (they see their own orders' progress
but don't act on the lab workflow itself).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_user,
    get_db,
    require_clinic_context,
    require_lab_manage_role,
    require_lab_template_manage_role,
    require_lab_view_role,
)
from app.models.user import User
from app.schemas.laboratory import (
    LaboratoryAttachmentCreate,
    LaboratoryAttachmentRead,
    LaboratoryOrderRead,
    LaboratoryResultsSubmit,
    LaboratoryTemplateCreate,
    LaboratoryTemplateRead,
    LaboratoryTemplateUpdate,
)
from app.services.laboratory_service import LaboratoryService

router = APIRouter(prefix="/laboratory", tags=["laboratory"])


@router.get("/dashboard")
async def get_dashboard(
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> dict:
    service = LaboratoryService(db)
    return await service.dashboard_stats(clinic_id=clinic_id)


@router.get("/orders", response_model=list[LaboratoryOrderRead])
async def list_orders(
    visit_id: UUID | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryOrderRead]:
    service = LaboratoryService(db)
    if visit_id is not None:
        return await service.list_for_visit(visit_id, clinic_id=clinic_id)
    return await service.list_for_dashboard(clinic_id=clinic_id)


@router.get("/orders/{laboratory_order_id}", response_model=LaboratoryOrderRead)
async def get_order(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).get(laboratory_order_id, clinic_id=clinic_id)


@router.post("/orders/{laboratory_order_id}/collect", response_model=LaboratoryOrderRead)
async def collect_specimen(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).collect_specimen(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/start-processing", response_model=LaboratoryOrderRead)
async def start_processing(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).start_processing(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/results", response_model=LaboratoryOrderRead)
async def enter_results(
    laboratory_order_id: UUID,
    payload: LaboratoryResultsSubmit,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    results = [r.model_dump() for r in payload.results]
    return await LaboratoryService(db).enter_results(laboratory_order_id, results, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/release", response_model=LaboratoryOrderRead)
async def release_results(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).release_results(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/cancel", response_model=LaboratoryOrderRead)
async def cancel_order(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    return await LaboratoryService(db).cancel_order(laboratory_order_id, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/orders/{laboratory_order_id}/attachments", response_model=LaboratoryOrderRead)
async def add_attachment(
    laboratory_order_id: UUID,
    payload: LaboratoryAttachmentCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_manage_role),
) -> LaboratoryOrderRead:
    service = LaboratoryService(db)
    await service.add_attachment(laboratory_order_id, payload.model_dump(), clinic_id=clinic_id, actor_id=current_user.id)
    return await service.get(laboratory_order_id, clinic_id=clinic_id)


@router.get("/orders/{laboratory_order_id}/attachments", response_model=list[LaboratoryAttachmentRead])
async def list_attachments(
    laboratory_order_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryAttachmentRead]:
    rows = await LaboratoryService(db).list_attachments(laboratory_order_id, clinic_id=clinic_id)
    return [LaboratoryAttachmentRead.model_validate(r, from_attributes=True) for r in rows]


# --- Templates ---

@router.get("/templates", response_model=list[LaboratoryTemplateRead])
async def list_templates(
    active_only: bool = False,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryTemplateRead]:
    return await LaboratoryService(db).list_templates(clinic_id=clinic_id, active_only=active_only)


@router.post("/templates", response_model=LaboratoryTemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: LaboratoryTemplateCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> LaboratoryTemplateRead:
    data = payload.model_dump()
    data["parameters"] = [p for p in data["parameters"]]
    return await LaboratoryService(db).create_template(data, clinic_id=clinic_id)


@router.patch("/templates/{template_id}", response_model=LaboratoryTemplateRead)
async def update_template(
    template_id: UUID,
    payload: LaboratoryTemplateUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_template_manage_role),
) -> LaboratoryTemplateRead:
    return await LaboratoryService(db).update_template(template_id, payload.model_dump(exclude_unset=True), clinic_id=clinic_id)


# --- Visit / Patient laboratory history (mounted under their own path prefixes) ---

visit_router = APIRouter(tags=["laboratory"])


@visit_router.get("/visits/{visit_id}/laboratory", response_model=list[LaboratoryOrderRead])
async def get_visit_laboratory(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryOrderRead]:
    return await LaboratoryService(db).list_for_visit(visit_id, clinic_id=clinic_id)


@visit_router.get("/patients/{patient_id}/laboratory", response_model=list[LaboratoryOrderRead])
async def get_patient_laboratory(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_lab_view_role),
) -> list[LaboratoryOrderRead]:
    return await LaboratoryService(db).list_for_patient(patient_id, clinic_id=clinic_id)
