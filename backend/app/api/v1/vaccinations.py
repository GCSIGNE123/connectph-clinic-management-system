"""Vaccination Administration endpoints (Post-RC1).

Role gating (see `core/dependencies.py`): Doctor still creates Vaccination-
category orders via the unchanged Phase 9 `/consultations/{id}/orders`
endpoint. Administering a vaccination - recording lot/site/route/dose and
marking it given - is deliberately broader than other clinical-order
categories: Nurse and Receptionist may administer in addition to the
ordering Doctor and Owner/Administrator, matching real clinic staffing
where front-desk/nursing staff routinely give injections a doctor ordered.
"""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_clinic_context,
    require_vaccination_administer_role,
    require_vaccination_view_role,
)
from app.models.user import User
from app.models.vaccination_administration import VaccinationStatus
from app.schemas.vaccination import VaccinationAdministerRequest, VaccinationAdministrationRead
from app.services.vaccination_service import VaccinationService

router = APIRouter(prefix="/vaccinations", tags=["vaccinations"])


@router.get("", response_model=list[VaccinationAdministrationRead])
async def list_vaccinations(
    status_filter: VaccinationStatus | None = None,
    patient_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vaccination_view_role),
) -> list[VaccinationAdministrationRead]:
    service = VaccinationService(db)
    if patient_id is not None:
        return await service.list_for_patient(patient_id, clinic_id)
    return await service.list_for_clinic(clinic_id, status_filter=status_filter, date_from=date_from, date_to=date_to)


@router.post("/{vaccination_id}/administer", response_model=VaccinationAdministrationRead)
async def administer_vaccination(
    vaccination_id: UUID,
    payload: VaccinationAdministerRequest,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vaccination_administer_role),
) -> VaccinationAdministrationRead:
    service = VaccinationService(db)
    return await service.administer(vaccination_id, payload, clinic_id=clinic_id, actor_id=current_user.id)


@router.post("/{vaccination_id}/cancel", response_model=VaccinationAdministrationRead)
async def cancel_vaccination(
    vaccination_id: UUID,
    clinic_id: UUID = Depends(require_clinic_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_vaccination_administer_role),
) -> VaccinationAdministrationRead:
    service = VaccinationService(db)
    return await service.cancel(vaccination_id, clinic_id=clinic_id, actor_id=current_user.id)
