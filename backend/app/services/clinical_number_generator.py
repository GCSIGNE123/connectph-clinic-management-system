"""Clinic-scoped, concurrency-safe number generators for Orders and
Prescriptions (Phase 9), following the same `system_settings`-backed
counter pattern as `PatientNumberGenerator` (a JSONB counter row locked
with `SELECT ... FOR UPDATE`), but date-scoped like `VisitNumberGenerator`
since order/prescription volume resets meaningfully per day.

Formats: `ORD-YYYYMMDD-000001`, `RX-YYYYMMDD-000001`.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

DEFAULT_PADDING = 6


class _DailyNumberGenerator:
    def __init__(self, session: AsyncSession, *, key_prefix: str, number_prefix: str) -> None:
        self.session = session
        self.key_prefix = key_prefix
        self.number_prefix = number_prefix

    def _key(self, counter_date: date) -> str:
        return f"{self.key_prefix}_{counter_date.strftime('%Y%m%d')}"

    async def _get_or_create_counter(self, clinic_id: UUID, counter_date: date) -> SystemSetting:
        key = self._key(counter_date)
        stmt = select(SystemSetting).where(SystemSetting.clinic_id == clinic_id, SystemSetting.key == key).with_for_update()
        result = await self.session.execute(stmt)
        counter = result.scalar_one_or_none()
        if counter is not None:
            return counter

        # First counter row for this clinic/day - concurrency-safe (see
        # BUG-013): a `SELECT ... FOR UPDATE` on a row that doesn't exist
        # yet takes no lock and blocks nothing, so two simultaneous
        # requests can both see "no row yet" here and both attempt the
        # INSERT below. `uq_system_setting_clinic_key` guarantees only one
        # of them can win; the loser must not surface that as a raw
        # IntegrityError/500 (BUG-013 fixed this exact race for
        # `AppointmentNumberGenerator` but explicitly left this shared
        # Order/Prescription counter unfixed - see that bug's writeup).
        # The INSERT attempt is wrapped in its own SAVEPOINT
        # (`begin_nested`) so a losing INSERT only unwinds itself, not the
        # whole request's transaction (everything else already flushed in
        # this transaction - e.g. a not-yet-committed `Order` row when
        # called from `ClinicalOrdersService.create_order` - survives the
        # loser's retry untouched).
        counter = SystemSetting(
            clinic_id=clinic_id, key=key, value={"next": 1},
            description=f"Auto-incrementing counter backing {self.__class__.__name__} for {counter_date.isoformat()}.",
        )
        try:
            async with self.session.begin_nested():
                self.session.add(counter)
                await self.session.flush()
        except IntegrityError:
            # Lost the race: the winner's row now exists. Re-select (still
            # `FOR UPDATE`, so we wait for and then hold the winner's row's
            # lock) and continue numbering from it instead of failing the
            # whole request.
            result = await self.session.execute(stmt)
            return result.scalar_one()

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def next_number(self, clinic_id: UUID, on_date: date | None = None, *, padding: int = DEFAULT_PADDING) -> str:
        counter_date = on_date or date.today()
        counter = await self._get_or_create_counter(clinic_id, counter_date)
        value = dict(counter.value or {})
        next_value = int(value.get("next", 1))
        value["next"] = next_value + 1
        counter.value = value
        await self.session.flush()
        date_part = counter_date.strftime("%Y%m%d")
        return f"{self.number_prefix}-{date_part}-{str(next_value).zfill(padding)}"


class OrderNumberGenerator(_DailyNumberGenerator):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, key_prefix="order_number_counter", number_prefix="ORD")


class PrescriptionNumberGenerator(_DailyNumberGenerator):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, key_prefix="prescription_number_counter", number_prefix="RX")


class MedicalCertificateNumberGenerator(_DailyNumberGenerator):
    """Format: `MC-YYYYMMDD-000001`. Only called at issue time (a Draft has
    no number yet) - see `MedicalCertificateService.issue`."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, key_prefix="medical_certificate_number_counter", number_prefix="MC")
