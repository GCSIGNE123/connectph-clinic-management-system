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

        counter = SystemSetting(
            clinic_id=clinic_id, key=key, value={"next": 1},
            description=f"Auto-incrementing counter backing {self.__class__.__name__} for {counter_date.isoformat()}.",
        )
        self.session.add(counter)
        await self.session.flush()
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
