"""Clinical Orders & Prescriptions endpoints (Phase 9).

Role gating (see `core/dependencies.py`): only the visit's assigned doctor
may create orders/procedures/referrals/prescriptions or update order
status; Owner/Administrator may view any (read-only, same pattern as Phase
8); Receptionist is read-only per this phase's spec wording ("Reception:
Read-only" - unlike Phase 8, where Receptionist was excluded entirely);
Laboratory role may view Laboratory-category orders only, read-only, no
access to Prescriptions/Procedures/Referrals/other-category orders.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    CLINICAL_ORDERS_PRIVILEGED_ROLES,
    get_db,
    require_clinic_context,
    require_clinical_orders_edit_role,
    require_clinical_orders_view_role,
)
from app.models.order import OrderCategory, OrderStatus
from app.models.user import User
from app.repositories.visit_repository import VisitRepository
from app.schemas.clinical_orders import (
    OrderCreate,
    OrderRead,
    OrderStatusUpdate,
    PrescriptionCreate,
    PrescriptionCreateResponse,
    PrescriptionRead,
    ProcedureCreate,
    ProcedureRead,
    ReferralCreate,
    ReferralRead,
)
from app.services.clinical_orders_service import ClinicalOrdersService

router = APIRouter(tags=["clinical-orders"])


def _is_privileged(user: User) -> bool:
    role_name = user.role.name if user.role is not None else None
    return role_name in CLINICAL_ORDERS_PRIVILEGED_ROLES


async def _permissions_for_consultation(db: AsyncSession, clinic_id: UUID, current_user: User, consultation_id: UUID) -> bool:
    """Resolves whether the current user may edit (create/update) clinical
    orders for this consultation - mirrors
    `api/v1/consultations.py::_require_visit_and_permissions` exactly."""
    from app.repositories.consultation_repository import ConsultationRepository

    consultation = await ConsultationRepository(db).get_by_id(consultation_id, clinic_id)
    if consultation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consultation not found")

    visit = await VisitRepository(db).get_by_id_and_clinic(consultation.visit_id, clinic_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")

    privileged = _is_privileged(current_user)
    if privileged:
        return False  # view-only, per Phase 8 pattern
    role_name = current_user.role.name if current_user.role is not None else None
    if role_name == "Receptionist":
        return False  # explicit read-only per spec
    can_edit = current_user.doctor_id is not None and current_user.doctor_id == visit.doctor_id
    return can_edit


@router.post("/consultations/{consultation_id}/orders", response_model=OrderRead)
async def create_order(
    consultation_id: UUID,
    payload: OrderCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_edit_role),
) -> OrderRead:
    can_edit = await _permissions_for_consultation(db, clinic_id, current_user, consultation_id)
    service = ClinicalOrdersService(db)
    return await service.create_order(consultation_id, payload, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.get("/consultations/{consultation_id}/orders", response_model=list[OrderRead])
async def list_orders(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[OrderRead]:
    service = ClinicalOrdersService(db)
    return await service.list_orders(consultation_id, clinic_id=clinic_id)


@router.patch("/orders/{order_id}/status", response_model=OrderRead)
async def update_order_status(
    order_id: UUID,
    payload: OrderStatusUpdate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_edit_role),
) -> OrderRead:
    from app.repositories.clinical_orders_repository import ClinicalOrdersRepository

    order = await ClinicalOrdersRepository(db).get_order(order_id, clinic_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    can_edit = await _permissions_for_consultation(db, clinic_id, current_user, order.consultation_id)
    service = ClinicalOrdersService(db)
    return await service.update_order_status(order_id, payload.status, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.post("/consultations/{consultation_id}/procedures", response_model=ProcedureRead)
async def create_procedure(
    consultation_id: UUID,
    payload: ProcedureCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_edit_role),
) -> ProcedureRead:
    can_edit = await _permissions_for_consultation(db, clinic_id, current_user, consultation_id)
    service = ClinicalOrdersService(db)
    return await service.create_procedure(consultation_id, payload, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.get("/consultations/{consultation_id}/procedures", response_model=list[ProcedureRead])
async def list_procedures(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[ProcedureRead]:
    service = ClinicalOrdersService(db)
    return await service.list_procedures(consultation_id, clinic_id=clinic_id)


@router.post("/consultations/{consultation_id}/referrals", response_model=ReferralRead)
async def create_referral(
    consultation_id: UUID,
    payload: ReferralCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_edit_role),
) -> ReferralRead:
    can_edit = await _permissions_for_consultation(db, clinic_id, current_user, consultation_id)
    service = ClinicalOrdersService(db)
    return await service.create_referral(consultation_id, payload, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.get("/consultations/{consultation_id}/referrals", response_model=list[ReferralRead])
async def list_referrals(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[ReferralRead]:
    service = ClinicalOrdersService(db)
    return await service.list_referrals(consultation_id, clinic_id=clinic_id)


@router.post("/consultations/{consultation_id}/prescriptions", response_model=PrescriptionCreateResponse)
async def create_prescription(
    consultation_id: UUID,
    payload: PrescriptionCreate,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_edit_role),
) -> PrescriptionCreateResponse:
    can_edit = await _permissions_for_consultation(db, clinic_id, current_user, consultation_id)
    service = ClinicalOrdersService(db)
    return await service.create_prescription(consultation_id, payload, clinic_id=clinic_id, actor_id=current_user.id, can_edit=can_edit)


@router.get("/consultations/{consultation_id}/prescriptions", response_model=list[PrescriptionRead])
async def list_prescriptions(
    consultation_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[PrescriptionRead]:
    service = ClinicalOrdersService(db)
    return await service.list_prescriptions(consultation_id, clinic_id=clinic_id)


@router.get("/visits/{visit_id}/orders", response_model=list[OrderRead])
async def list_visit_orders(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[OrderRead]:
    service = ClinicalOrdersService(db)
    return await service.list_orders_for_visit(visit_id, clinic_id=clinic_id)


@router.get("/visits/{visit_id}/procedures", response_model=list[ProcedureRead])
async def list_visit_procedures(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[ProcedureRead]:
    service = ClinicalOrdersService(db)
    return await service.list_procedures_for_visit(visit_id, clinic_id=clinic_id)


@router.get("/visits/{visit_id}/referrals", response_model=list[ReferralRead])
async def list_visit_referrals(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[ReferralRead]:
    service = ClinicalOrdersService(db)
    return await service.list_referrals_for_visit(visit_id, clinic_id=clinic_id)


@router.get("/visits/{visit_id}/prescriptions", response_model=list[PrescriptionRead])
async def list_visit_prescriptions(
    visit_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[PrescriptionRead]:
    service = ClinicalOrdersService(db)
    return await service.list_prescriptions_for_visit(visit_id, clinic_id=clinic_id)


@router.get("/patients/{patient_id}/prescriptions", response_model=list[PrescriptionRead])
async def list_patient_prescriptions(
    patient_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_clinical_orders_view_role),
) -> list[PrescriptionRead]:
    service = ClinicalOrdersService(db)
    return await service.list_prescriptions_for_patient(patient_id, clinic_id=clinic_id)


# NOTE (Phase 10): the Phase-9 placeholder `GET /laboratory/orders` that
# used to live here (Laboratory-role, visit_id-only, raw `OrderRead` shape)
# has been superseded by the full Laboratory Management module's own
# `GET /api/v1/laboratory/orders` in `api/v1/laboratory.py`, which supports
# both the dashboard worklist (no visit_id) and the visit-scoped list, with
# the richer `LaboratoryOrderRead` shape (status/results/collection-
# timestamps) the Laboratory Dashboard needs. Removed here to avoid two
# routers claiming the same path - see `laboratory.py` instead.
