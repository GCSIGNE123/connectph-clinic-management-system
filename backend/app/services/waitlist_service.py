"""Waitlist (Phase 11) - architecture-level "offer" on cancellation.

No SMS/email/push is sent (out of scope); `offer_next_slot` makes the offer
a real, queryable state change (`WaitlistEntry.status -> Offered` with the
freed slot recorded) that a future notification phase would consume.
"""

from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import WaitlistEntry, WaitlistStatus
from app.schemas.appointment import WaitlistEntryCreate, WaitlistEntryRead


class WaitlistService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_entry(self, payload: WaitlistEntryCreate, *, clinic_id: UUID, actor_id: UUID) -> WaitlistEntryRead:
        entry = WaitlistEntry(
            clinic_id=clinic_id, patient_id=payload.patient_id, doctor_id=payload.doctor_id,
            branch_id=payload.branch_id, date_from=payload.date_from, date_to=payload.date_to,
            status=WaitlistStatus.WAITING, notes=payload.notes, created_by=actor_id,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return WaitlistEntryRead.model_validate(entry)

    async def offer_next_slot(
        self, *, clinic_id: UUID, doctor_id: UUID, freed_date: date, freed_start_time: time
    ) -> WaitlistEntryRead | None:
        stmt = (
            select(WaitlistEntry)
            .where(
                WaitlistEntry.clinic_id == clinic_id,
                WaitlistEntry.doctor_id == doctor_id,
                WaitlistEntry.status == WaitlistStatus.WAITING,
                WaitlistEntry.date_from <= freed_date,
                WaitlistEntry.date_to >= freed_date,
                WaitlistEntry.is_deleted.is_(False),
            )
            .order_by(WaitlistEntry.created_at.asc())
            .limit(1)
        )
        entry = (await self.session.execute(stmt)).scalar_one_or_none()
        if entry is None:
            return None
        entry.status = WaitlistStatus.OFFERED
        entry.offered_slot_date = freed_date
        entry.offered_slot_start_time = freed_start_time
        await self.session.commit()
        await self.session.refresh(entry)
        return WaitlistEntryRead.model_validate(entry)

    async def list_for_doctor(self, *, clinic_id: UUID, doctor_id: UUID) -> list[WaitlistEntryRead]:
        stmt = select(WaitlistEntry).where(
            WaitlistEntry.clinic_id == clinic_id, WaitlistEntry.doctor_id == doctor_id, WaitlistEntry.is_deleted.is_(False)
        ).order_by(WaitlistEntry.created_at.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return [WaitlistEntryRead.model_validate(r) for r in rows]
