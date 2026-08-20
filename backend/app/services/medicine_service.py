"""Medicine Inventory Phase 1: catalog (Medicine) + batch/lot CRUD.

Status computation: `MedicineBatch.status` is a cached/computed value, not a
free-standing client-authoritative field (see `models/medicine.py`'s module
docstring). `_compute_status` is the single source of truth for the
ACTIVE/EXPIRED/DEPLETED rules and is applied on every create/update AND on
every read (`_refresh_status`), so Phase 1 stays accurate with no background
job. RECALLED is the one manual exception - once a batch is marked
Recalled, `_refresh_status` leaves it alone until a caller explicitly sets a
different status. A future Phase 3 daily job can call this exact same
`_compute_status` helper instead of duplicating the rule.
"""

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medicine import Medicine, MedicineBatch, MedicineBatchStatus
from app.models.user import User
from app.repositories.medicine_batch_repository import MedicineBatchRepository
from app.repositories.medicine_repository import MedicineRepository
from app.schemas.medicine import (
    MedicineBatchCreate,
    MedicineBatchUpdate,
    MedicineCreate,
    MedicineSearchParams,
    MedicineUpdate,
)
from app.services.audit_service import AuditService


def _compute_status(batch: MedicineBatch, *, today: date | None = None) -> MedicineBatchStatus:
    if batch.status == MedicineBatchStatus.RECALLED:
        return MedicineBatchStatus.RECALLED
    reference_date = today or date.today()
    if batch.expiry_date < reference_date:
        return MedicineBatchStatus.EXPIRED
    if batch.quantity_remaining <= 0:
        return MedicineBatchStatus.DEPLETED
    return MedicineBatchStatus.ACTIVE


class MedicineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MedicineRepository(session)
        self.batch_repo = MedicineBatchRepository(session)
        self.audit_service = AuditService(session)

    # --- Medicine catalog ---

    async def search(self, clinic_id: UUID, params: MedicineSearchParams) -> tuple[list[Medicine], int]:
        return await self.repo.search(clinic_id, params)

    async def get(self, medicine_id: UUID, clinic_id: UUID) -> Medicine:
        medicine = await self.repo.get_by_id_and_clinic(medicine_id, clinic_id)
        if medicine is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medicine not found")
        return medicine

    async def create(self, payload: MedicineCreate, *, clinic_id: UUID, actor: User) -> Medicine:
        medicine = await self.repo.create(clinic_id=clinic_id, **payload.model_dump())
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="medicine.created",
            entity_type="medicine", entity_id=str(medicine.id),
        )
        await self.session.commit()
        return await self.get(medicine.id, clinic_id)

    async def update(self, medicine_id: UUID, payload: MedicineUpdate, *, clinic_id: UUID, actor: User) -> Medicine:
        medicine = await self.get(medicine_id, clinic_id)
        updates = payload.model_dump(exclude_unset=True)
        medicine = await self.repo.update(medicine, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="medicine.updated",
            entity_type="medicine", entity_id=str(medicine_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get(medicine.id, clinic_id)

    async def delete(self, medicine_id: UUID, *, clinic_id: UUID, actor: User) -> None:
        medicine = await self.get(medicine_id, clinic_id)
        await self.repo.delete(medicine, soft=True)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="medicine.deleted",
            entity_type="medicine", entity_id=str(medicine_id),
        )
        await self.session.commit()

    # --- Batches ---

    async def list_batches(self, medicine_id: UUID, *, clinic_id: UUID) -> list[MedicineBatch]:
        await self.get(medicine_id, clinic_id)  # 404s if the medicine isn't in this clinic
        batches = await self.batch_repo.list_for_medicine(medicine_id, clinic_id)
        changed = False
        for batch in batches:
            recomputed = _compute_status(batch)
            if recomputed != batch.status:
                batch.status = recomputed
                changed = True
        if changed:
            await self.session.commit()
        return batches

    async def get_batch(self, medicine_id: UUID, batch_id: UUID, *, clinic_id: UUID) -> MedicineBatch:
        await self.get(medicine_id, clinic_id)
        batch = await self.batch_repo.get_by_id_and_clinic(batch_id, clinic_id)
        if batch is None or batch.medicine_id != medicine_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")
        recomputed = _compute_status(batch)
        if recomputed != batch.status:
            batch.status = recomputed
            await self.session.commit()
        return batch

    async def create_batch(
        self, medicine_id: UUID, payload: MedicineBatchCreate, *, clinic_id: UUID, actor: User
    ) -> MedicineBatch:
        # Confirms the medicine belongs to THIS clinic before any batch can be
        # attached to it - the one explicit cross-tenant guard the task calls
        # out ("do not allow batch records to point to another clinic's
        # medicine"); `medicine_id` alone is never trusted from the URL.
        await self.get(medicine_id, clinic_id)

        existing = await self.batch_repo.get_by_number(medicine_id, payload.batch_number, clinic_id)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Batch number already in use for this medicine")

        data = payload.model_dump()
        try:
            batch = await self.batch_repo.create(clinic_id=clinic_id, medicine_id=medicine_id, **data)
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Batch number already in use for this medicine"
            ) from None

        batch.status = _compute_status(batch)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="medicine_batch.created",
            entity_type="medicine_batch", entity_id=str(batch.id),
            metadata={
                "medicine_id": str(medicine_id), "batch_number": batch.batch_number,
                "quantity_received": batch.quantity_received, "expiry_date": batch.expiry_date.isoformat(),
            },
        )
        await self.session.commit()
        return await self.get_batch(medicine_id, batch.id, clinic_id=clinic_id)

    async def update_batch(
        self, medicine_id: UUID, batch_id: UUID, payload: MedicineBatchUpdate, *, clinic_id: UUID, actor: User
    ) -> MedicineBatch:
        batch = await self.get_batch(medicine_id, batch_id, clinic_id=clinic_id)
        updates = payload.model_dump(exclude_unset=True)

        if "status" in updates and updates["status"] != MedicineBatchStatus.RECALLED:
            # ACTIVE/EXPIRED/DEPLETED are always computed - a client may only
            # ever explicitly set RECALLED (a real business action); any
            # other explicit value is rejected rather than silently ignored,
            # so a caller never believes a manual status stuck when it didn't.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="status can only be explicitly set to 'Recalled' - other statuses are computed automatically",
            )

        if "batch_number" in updates and updates["batch_number"] != batch.batch_number:
            existing = await self.batch_repo.get_by_number(medicine_id, updates["batch_number"], clinic_id)
            if existing is not None and existing.id != batch_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Batch number already in use for this medicine")

        new_received = updates.get("quantity_received", batch.quantity_received)
        new_remaining = updates.get("quantity_remaining", batch.quantity_remaining)
        if new_remaining > new_received:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="quantity_remaining cannot exceed quantity_received",
            )

        try:
            batch = await self.batch_repo.update(batch, **updates)
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Batch number already in use for this medicine") from None

        batch.status = _compute_status(batch)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="medicine_batch.updated",
            entity_type="medicine_batch", entity_id=str(batch_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.get_batch(medicine_id, batch.id, clinic_id=clinic_id)
