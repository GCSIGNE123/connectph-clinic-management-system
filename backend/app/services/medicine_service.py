"""Medicine Inventory: catalog (Medicine) + batch/lot CRUD (Phase 1) + stock
movement ledger (Phase 2, `create_movement`/`list_movements`).

Status computation: `MedicineBatch.status` is a cached/computed value, not a
free-standing client-authoritative field (see `models/medicine.py`'s module
docstring). `_compute_status` is the single source of truth for the
ACTIVE/EXPIRED/DEPLETED rules and is applied on every create/update/movement
AND on every read, so this stays accurate with no background job. RECALLED
is the one manual exception - once a batch is marked Recalled, recompute
leaves it alone until a caller explicitly changes it. A future Phase 3 daily
job can call this exact same `_compute_status` helper instead of
duplicating the rule.

Phase 2 concurrency: `create_movement` locks the batch row with
`SELECT ... FOR UPDATE` (`MedicineBatchRepository.get_for_update`) before
reading its current quantity, computing the new quantity, and updating it -
the same pattern `VisitNumberGenerator`/`QueueNumberGenerator` use for their
counter rows - so two concurrent movements against the same batch serialize
instead of racing. The movement INSERT and the batch quantity UPDATE happen
in the same session and are committed together in a single `session.
commit()` call; if anything raises before that commit (validation error,
IntegrityError, etc.) nothing is flushed to a durable state the caller can
observe as committed, so neither the movement row nor the quantity change
"partially" applies.
"""

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic import Clinic
from app.models.medicine import (
    Medicine,
    MedicineBatch,
    MedicineBatchStatus,
    MedicineStockMovement,
    MedicineStockMovementType,
)
from app.models.user import User
from app.repositories.medicine_batch_repository import MedicineBatchRepository
from app.repositories.medicine_repository import MedicineRepository
from app.repositories.medicine_stock_movement_repository import MedicineStockMovementRepository
from app.schemas.medicine import (
    MedicineBatchCreate,
    MedicineBatchUpdate,
    MedicineCreate,
    MedicineSearchParams,
    MedicineStockMovementCreate,
    MedicineUpdate,
)
from app.services.audit_service import AuditService
from app.services.medicine_expiry_logic import ExpiryThresholds, is_expired, is_near_expiry

# Movement types whose sign is fixed (rather than caller-chosen, like
# ADJUSTMENT) - validated in `_validate_movement_delta`.
_POSITIVE_ONLY_TYPES = {MedicineStockMovementType.RECEIVED}
_NEGATIVE_ONLY_TYPES = {
    MedicineStockMovementType.DISPENSED,
    MedicineStockMovementType.EXPIRED,
    MedicineStockMovementType.RECALLED,
}
# Movement types that must carry a `reason` - required for audit quality on
# anything that isn't a routine stock receipt (RECEIVED's reason is
# optional, e.g. a PO number, but never mandatory).
_REASON_REQUIRED_TYPES = {
    MedicineStockMovementType.ADJUSTMENT,
    MedicineStockMovementType.EXPIRED,
    MedicineStockMovementType.RECALLED,
}


def _compute_status(batch: MedicineBatch, *, today: date | None = None) -> MedicineBatchStatus:
    if batch.status == MedicineBatchStatus.RECALLED:
        return MedicineBatchStatus.RECALLED
    reference_date = today or date.today()
    if batch.expiry_date < reference_date:
        return MedicineBatchStatus.EXPIRED
    if batch.quantity_remaining <= 0:
        return MedicineBatchStatus.DEPLETED
    return MedicineBatchStatus.ACTIVE


def _active_batches(medicine: Medicine) -> list[MedicineBatch]:
    # Recalled batches are excluded from stock/expiry aggregation entirely -
    # they're a resolved, handled state, not part of "how much do we have
    # available" or "what's expiring soon" (matches
    # `medicine_expiry_logic.compute_expiry_tier`'s own Recalled exclusion).
    return [b for b in medicine.batches if not b.is_deleted and b.status != MedicineBatchStatus.RECALLED]


def _medicine_stock_categories(medicine: Medicine, thresholds: ExpiryThresholds, *, today: date | None = None) -> set[str]:
    """One medicine can be simultaneously "near expiry" (one batch) and
    "in stock" (another valid batch), or have an expired batch alongside a
    perfectly good one - this returns every applicable category rather than
    forcing a single label, so filtering never has to guess. See
    `_summarize_stock_status` for the single-label version used for display."""
    batches = _active_batches(medicine)
    if not batches:
        return {"out_of_stock"}

    total_remaining = sum(b.quantity_remaining for b in batches)
    categories: set[str] = set()
    if total_remaining <= 0:
        categories.add("out_of_stock")
    else:
        categories.add("in_stock")
        if medicine.reorder_level is not None and total_remaining <= medicine.reorder_level:
            categories.add("low_stock")
    if any(is_expired(b, today=today) for b in batches):
        categories.add("expired")
    if any(is_near_expiry(b, thresholds, today=today) for b in batches):
        categories.add("near_expiry")
    return categories


# Priority order (most urgent first) for the single-label summary shown on
# the medicine list row - filtering itself uses the full category set above,
# never just this one label.
_STATUS_PRIORITY = ["expired", "near_expiry", "out_of_stock", "low_stock", "in_stock"]


def _summarize_stock_status(categories: set[str]) -> str:
    for label in _STATUS_PRIORITY:
        if label in categories:
            return label
    return "in_stock"  # pragma: no cover - categories is never empty in practice


async def _get_thresholds(session: AsyncSession, clinic_id: UUID) -> ExpiryThresholds:
    clinic = (await session.execute(select(Clinic).where(Clinic.id == clinic_id))).scalar_one()
    return ExpiryThresholds(
        tier1=clinic.medicine_expiry_warning_days_tier1, tier2=clinic.medicine_expiry_warning_days_tier2,
        tier3=clinic.medicine_expiry_warning_days_tier3, tier4=clinic.medicine_expiry_warning_days_tier4,
    )


def _validate_movement_delta(movement_type: MedicineStockMovementType, quantity_delta: int, reason: str | None) -> None:
    if movement_type in _POSITIVE_ONLY_TYPES and quantity_delta <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{movement_type.value} requires a positive quantity_delta",
        )
    if movement_type in _NEGATIVE_ONLY_TYPES and quantity_delta >= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{movement_type.value} requires a negative quantity_delta",
        )
    if movement_type in _REASON_REQUIRED_TYPES and not (reason and reason.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{movement_type.value} requires a reason",
        )


class MedicineService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = MedicineRepository(session)
        self.batch_repo = MedicineBatchRepository(session)
        self.movement_repo = MedicineStockMovementRepository(session)
        self.audit_service = AuditService(session)

    # --- Medicine catalog ---

    async def search(self, clinic_id: UUID, params: MedicineSearchParams) -> tuple[list[tuple[Medicine, str]], int]:
        """Returns `(medicine, stock_status_label)` pairs (see
        `_summarize_stock_status`) plus the total AFTER any `stock_status`
        filter is applied. Pagination happens here, in Python, over the
        full eager-loaded result - see `MedicineRepository.search_with_
        batches`'s docstring for why."""
        thresholds = await _get_thresholds(self.session, clinic_id)
        medicines = await self.repo.search_with_batches(clinic_id, params)

        today = date.today()
        results = [(m, _medicine_stock_categories(m, thresholds, today=today)) for m in medicines]
        if params.stock_status:
            results = [(m, cats) for m, cats in results if params.stock_status in cats]

        total = len(results)
        page = results[params.offset : params.offset + params.limit]
        return [(m, _summarize_stock_status(cats)) for m, cats in page], total

    async def get_stats(self, clinic_id: UUID) -> dict[str, int]:
        """Medicine-level counts for the dashboard stat cards / filter
        chips - each medicine counted at most once per category, matching
        `search`'s own per-medicine (not per-batch) categorization."""
        thresholds = await _get_thresholds(self.session, clinic_id)
        medicines = await self.repo.list_all_active_with_batches(clinic_id)
        today = date.today()

        counts = {"expiring_soon": 0, "expired": 0, "low_stock": 0, "out_of_stock": 0}
        for medicine in medicines:
            categories = _medicine_stock_categories(medicine, thresholds, today=today)
            if "near_expiry" in categories:
                counts["expiring_soon"] += 1
            if "expired" in categories:
                counts["expired"] += 1
            if "low_stock" in categories:
                counts["low_stock"] += 1
            if "out_of_stock" in categories:
                counts["out_of_stock"] += 1
        return counts

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

    # --- Stock movement ledger (Phase 2) ---

    async def list_movements(self, medicine_id: UUID, batch_id: UUID, *, clinic_id: UUID) -> list[MedicineStockMovement]:
        await self.get_batch(medicine_id, batch_id, clinic_id=clinic_id)  # 404s on cross-tenant/mismatched batch
        return await self.movement_repo.list_for_batch(batch_id, clinic_id)

    async def create_movement(
        self, medicine_id: UUID, batch_id: UUID, payload: MedicineStockMovementCreate, *, clinic_id: UUID, actor: User
    ) -> MedicineStockMovement:
        # Confirms the medicine belongs to this clinic and the batch belongs
        # to that medicine, same cross-tenant guard as `create_batch` -
        # before taking any lock or touching quantities.
        await self.get(medicine_id, clinic_id)

        _validate_movement_delta(payload.movement_type, payload.quantity_delta, payload.reason)

        # Row lock: everything from here until `session.commit()` below must
        # see a consistent snapshot of this batch's quantity, and no other
        # concurrent movement against the same batch may read/write it until
        # this transaction commits or rolls back. See module docstring.
        batch = await self.batch_repo.get_for_update(batch_id, medicine_id, clinic_id)
        if batch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found")

        new_remaining = batch.quantity_remaining + payload.quantity_delta
        new_received = batch.quantity_received
        if payload.movement_type == MedicineStockMovementType.RECEIVED:
            # New stock physically arriving under this batch/lot raises the
            # cap by the same amount it raises the balance - otherwise a
            # legitimate restock would immediately violate
            # quantity_remaining <= quantity_received.
            new_received = batch.quantity_received + payload.quantity_delta

        if new_remaining < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This movement would reduce quantity below zero",
            )
        if new_remaining > new_received:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This movement would exceed the batch's received quantity",
            )

        batch.quantity_remaining = new_remaining
        batch.quantity_received = new_received
        if payload.movement_type == MedicineStockMovementType.RECALLED:
            # Explicit business action, same override semantics as the
            # Phase 1 manual status=Recalled path - preserves the batch as a
            # historical record regardless of remaining quantity.
            batch.status = MedicineBatchStatus.RECALLED
        else:
            batch.status = _compute_status(batch)

        movement = MedicineStockMovement(
            clinic_id=clinic_id,
            batch_id=batch.id,
            movement_type=payload.movement_type,
            quantity_delta=payload.quantity_delta,
            resulting_quantity=new_remaining,
            reason=payload.reason,
            performed_by=actor.id,
        )
        self.session.add(movement)
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="inventory.stock_movement",
            entity_type="medicine_batch", entity_id=str(batch.id),
            metadata={
                "medicine_id": str(medicine_id), "batch_number": batch.batch_number,
                "movement_type": payload.movement_type.value, "quantity_delta": payload.quantity_delta,
                "reason": payload.reason, "resulting_quantity": new_remaining,
            },
        )
        movement_id = movement.id
        await self.session.commit()
        # Re-fetch rather than reading attributes off the just-committed
        # `movement` instance - same pattern `create_batch`/`update_batch`
        # use (`return await self.get_batch(...)` after commit) to avoid
        # touching a possibly-expired ORM instance; this also eager-loads
        # `performed_by_user` for `MedicineStockMovementRead.performed_by_name`.
        return await self.movement_repo.get_by_id_with_actor(movement_id, clinic_id)
