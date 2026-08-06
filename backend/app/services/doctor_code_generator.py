"""Configurable, clinic-scoped doctor code generation.

Parallel to `PatientNumberGenerator` - see that module's docstring for the
rationale (counter stored in `system_settings`, `SELECT ... FOR UPDATE` for
concurrency safety). Kept as a separate small class (rather than refactoring
`PatientNumberGenerator` into a generic base) to avoid touching the
already-shipped Phase 3 patient code path.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

DOCTOR_CODE_COUNTER_KEY = "doctor_code_counter"

DEFAULT_PREFIX = "DOC-"
DEFAULT_PADDING = 4


class DoctorCodeGenerator:
    """Generates sequential, clinic-scoped doctor codes like `DOC-0001`."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_or_create_counter(self, clinic_id: UUID) -> SystemSetting:
        stmt = (
            select(SystemSetting)
            .where(SystemSetting.clinic_id == clinic_id, SystemSetting.key == DOCTOR_CODE_COUNTER_KEY)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        counter = result.scalar_one_or_none()
        if counter is None:
            counter = SystemSetting(
                clinic_id=clinic_id,
                key=DOCTOR_CODE_COUNTER_KEY,
                value={"prefix": DEFAULT_PREFIX, "padding": DEFAULT_PADDING, "next": 1},
                description="Auto-incrementing counter backing DoctorCodeGenerator.",
            )
            self.session.add(counter)
            await self.session.flush()
            result = await self.session.execute(stmt)
            counter = result.scalar_one()
        return counter

    async def next_code(self, clinic_id: UUID) -> str:
        counter = await self._get_or_create_counter(clinic_id)
        value = dict(counter.value or {})
        prefix = value.get("prefix", DEFAULT_PREFIX)
        padding = int(value.get("padding", DEFAULT_PADDING))
        next_value = int(value.get("next", 1))

        doctor_code = f"{prefix}{str(next_value).zfill(padding)}"

        value["next"] = next_value + 1
        counter.value = value
        await self.session.flush()

        return doctor_code
