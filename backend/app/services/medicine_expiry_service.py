"""Medicine Inventory Phase 3: daily expiry-alert background job.

No Celery/APScheduler/cron exists in this backend - the only precedent is a
hand-rolled asyncio background loop (`connectivity_service.py`/
`sync_worker_service.py`: module-level task, `start_background_loop()`/
`stop_background_loop()`, `while True: ... await asyncio.sleep(...)`,
started/stopped from `app/main.py`'s lifespan). This module follows that
exact shape, with one addition those two don't need: a persisted "have I
already run today" guard, since this job must run AT MOST ONCE PER DAY
(the two existing loops are simple fixed-interval pollers with no such
constraint).

Guard mechanism: a per-clinic `SystemSetting` row (key
`medicine_expiry_check_last_run_date`), read with `SELECT ... FOR UPDATE`
and updated in the SAME transaction as every notification/tier-update this
run produces, committed together - the exact concurrency pattern
`_DailyNumberGenerator` (`clinical_number_generator.py`) already uses for
its counter rows, including the insert-race handling (two workers racing to
create the FIRST guard row for a clinic that has never run before). Because
the guard's `SELECT ... FOR UPDATE` is taken before any processing and held
until the final `commit()`, a second worker attempting the same clinic
blocks on that lock until the first worker's run is fully committed, then
observes `last_run_date == today` and skips - "safe if two workers
accidentally start the check" and "survive restarts without duplicates"
both fall out of this one mechanism, with no in-memory state at all.

Date convention: UTC date (`datetime.now(UTC).date()`), matching this
codebase's established fix for the exact class of bug `date.today()`
(local/server time) previously caused for the TV Display feature - not
per-clinic timezone, which is out of scope here.

Deduplication: see `models/medicine.py`'s `EXPIRY_TIER_*` docstring and
`medicine_expiry_logic.compute_expiry_tier` - a notification is generated
only when a batch's freshly-computed tier is strictly greater than its
stored `last_alerted_expiry_tier`, and that field is then advanced to the
new tier (never regenerated for the same or a lower tier). If an
administrator tightens the thresholds later such that a batch's computed
tier jumps by more than one level in a single day's run (e.g. from
"no alert yet" straight to tier 3 because tier 1/tier 2 were removed or
shortened past the batch's current days-remaining), this design generates
exactly ONE notification for the new current tier - it does NOT backfill
the skipped intermediate tiers, so tightening thresholds can never flood
users with a burst of catch-up alerts. Loosening thresholds (raising the
day counts) never re-lowers `last_alerted_expiry_tier`, so a batch that
already alerted at tier 3 will not re-alert at the (now further away) tier
1/2 thresholds either - forward-only.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.clinic import Clinic
from app.models.medicine import EXPIRY_TIER_EXPIRED, Medicine, MedicineBatch
from app.models.system_setting import SystemSetting
from app.services.audit_service import AuditService
from app.services.medicine_expiry_logic import ExpiryThresholds, compute_expiry_tier
from app.services.notification_service import NotificationService

logger = logging.getLogger("app.medicine_expiry")

CHECK_INTERVAL_SECONDS = 3600  # hourly poll; the daily guard makes extra polls cheap no-ops
GUARD_KEY = "medicine_expiry_check_last_run_date"
ALERT_TARGET_ROLES = ("Receptionist", "Doctor")


def _format_medicine_name(medicine: Medicine) -> str:
    parts = [medicine.generic_name]
    if medicine.brand_name:
        parts[0] = f"{medicine.generic_name} ({medicine.brand_name})"
    if medicine.strength:
        parts.append(medicine.strength)
    return " ".join(parts)


class MedicineExpiryCheckService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notification_service = NotificationService(session)
        self.audit_service = AuditService(session)

    async def _get_or_create_guard(self, clinic_id: UUID) -> SystemSetting:
        stmt = (
            select(SystemSetting)
            .where(SystemSetting.clinic_id == clinic_id, SystemSetting.key == GUARD_KEY)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        guard = result.scalar_one_or_none()
        if guard is not None:
            return guard

        guard = SystemSetting(
            clinic_id=clinic_id, key=GUARD_KEY, value={"last_run_date": None},
            description="Tracks the last UTC date the medicine expiry check ran for this clinic (Phase 3).",
        )
        try:
            async with self.session.begin_nested():
                self.session.add(guard)
                await self.session.flush()
        except IntegrityError:
            # Lost the race to create the first guard row - re-select
            # (still FOR UPDATE, so this waits for and then holds the
            # winner's row's lock) and let the caller's own date check
            # decide whether there's still anything to do.
            result = await self.session.execute(stmt)
            return result.scalar_one()

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def run_for_clinic(self, clinic_id: UUID, *, today: date | None = None) -> bool:
        """Returns True if this call actually ran the check (False if it was
        already run today - by this call or a concurrent one)."""
        today = today or datetime.now(UTC).date()
        guard = await self._get_or_create_guard(clinic_id)
        already_ran = (guard.value or {}).get("last_run_date") == today.isoformat()
        if already_ran:
            return False

        alerts_created = await self._process_clinic(clinic_id, today)

        guard.value = {"last_run_date": today.isoformat()}
        if alerts_created:
            await self.audit_service.log_event(
                clinic_id=clinic_id, action="inventory.expiry_check_run",
                metadata={"date": today.isoformat(), "alerts_created": alerts_created},
            )
        await self.session.commit()
        return True

    async def _process_clinic(self, clinic_id: UUID, today: date) -> int:
        clinic = (await self.session.execute(select(Clinic).where(Clinic.id == clinic_id))).scalar_one_or_none()
        if clinic is None:
            return 0
        thresholds = ExpiryThresholds(
            tier1=clinic.medicine_expiry_warning_days_tier1, tier2=clinic.medicine_expiry_warning_days_tier2,
            tier3=clinic.medicine_expiry_warning_days_tier3, tier4=clinic.medicine_expiry_warning_days_tier4,
        )

        stmt = (
            select(MedicineBatch, Medicine)
            .join(Medicine, MedicineBatch.medicine_id == Medicine.id)
            .where(
                MedicineBatch.clinic_id == clinic_id, MedicineBatch.is_deleted.is_(False),
                Medicine.is_deleted.is_(False), MedicineBatch.quantity_remaining > 0,
            )
        )
        rows = (await self.session.execute(stmt)).all()

        alerts_created = 0
        for batch, medicine in rows:
            tier = compute_expiry_tier(batch, thresholds, today=today)
            if tier <= batch.last_alerted_expiry_tier or tier == 0:
                continue

            name = _format_medicine_name(medicine)

            if tier == EXPIRY_TIER_EXPIRED:
                title = "Medicine Expired"
                body = (
                    f"{name}, Batch {batch.batch_number}, has {batch.quantity_remaining} units remaining "
                    f"and expired on {batch.expiry_date.strftime('%B %d, %Y')}."
                )
                notification_type = "medicine_expired"
            else:
                days_remaining = (batch.expiry_date - today).days
                title = "Medicine Expiring Soon"
                body = (
                    f"{name}, Batch {batch.batch_number}, has {batch.quantity_remaining} units remaining "
                    f"and expires in {days_remaining} day{'s' if days_remaining != 1 else ''}."
                )
                notification_type = "medicine_expiry_warning"

            for role in ALERT_TARGET_ROLES:
                await self.notification_service.create_role_notification(
                    clinic_id=clinic_id, target_role=role, type_=notification_type, title=title, body=body,
                    entity_type="medicine", entity_id=medicine.id,
                )
                alerts_created += 1

            batch.last_alerted_expiry_tier = tier

        return alerts_created


async def run_all_clinics(*, today: date | None = None) -> None:
    """Entry point for both the background loop and manual/test invocation.
    Each clinic gets its own transaction (own guard lock), so one clinic's
    failure can't roll back another's already-committed work."""
    async with AsyncSessionLocal() as session:
        clinic_ids = (await session.execute(select(Clinic.id).where(Clinic.is_deleted.is_(False)))).scalars().all()

    for clinic_id in clinic_ids:
        async with AsyncSessionLocal() as session:
            service = MedicineExpiryCheckService(session)
            try:
                await service.run_for_clinic(clinic_id, today=today)
            except Exception:
                logger.exception("Medicine expiry check failed for clinic %s", clinic_id)


async def _background_loop() -> None:  # pragma: no cover - exercised via manual/live verification
    while True:
        try:
            await run_all_clinics()
        except Exception:
            logger.exception("Medicine expiry background loop failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


_background_task: asyncio.Task | None = None


def start_background_loop() -> None:
    global _background_task
    if _background_task is None or _background_task.done():
        loop = asyncio.get_event_loop()
        _background_task = loop.create_task(_background_loop())


def stop_background_loop() -> None:
    global _background_task
    if _background_task is not None:
        _background_task.cancel()
        _background_task = None
