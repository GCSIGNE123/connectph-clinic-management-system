"""Configurable, clinic-scoped patient number generation.

Patient numbers must be unique per clinic and safe under concurrent inserts.
Rather than a raw Postgres SEQUENCE (which is global/DDL-managed and not
easily reconfigurable per clinic), the counter is stored as a row in
`system_settings` (key="patient_number_counter") whose JSONB value carries
the configurable prefix/padding/next-value. This lets a future admin UI
let a clinic customize its own numbering scheme (e.g. a different prefix
per branch) without a schema migration.

Concurrency: the counter row is fetched with `SELECT ... FOR UPDATE` inside
the caller's transaction, so two concurrent patient-creation requests for
the same clinic serialize on that row rather than racing on `next`.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

PATIENT_NUMBER_COUNTER_KEY = "patient_number_counter"

DEFAULT_PREFIX = "PAT-"
DEFAULT_PADDING = 6


class PatientNumberGenerator:
    """Generates sequential, clinic-scoped patient numbers like `PAT-000001`.

    Usage: `await PatientNumberGenerator(session).next_number(clinic_id)`
    within the same transaction that will insert the new patient row, so the
    counter increment and the patient insert commit/rollback together.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _get_or_create_counter(self, clinic_id: UUID) -> SystemSetting:
        stmt = (
            select(SystemSetting)
            .where(SystemSetting.clinic_id == clinic_id, SystemSetting.key == PATIENT_NUMBER_COUNTER_KEY)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        counter = result.scalar_one_or_none()
        if counter is None:
            counter = SystemSetting(
                clinic_id=clinic_id,
                key=PATIENT_NUMBER_COUNTER_KEY,
                value={"prefix": DEFAULT_PREFIX, "padding": DEFAULT_PADDING, "next": 1},
                description="Auto-incrementing counter backing PatientNumberGenerator.",
            )
            self.session.add(counter)
            await self.session.flush()
            # Re-select with FOR UPDATE to hold the lock for the remainder of
            # this transaction, consistent with the existing-row path.
            result = await self.session.execute(stmt)
            counter = result.scalar_one()
        return counter

    async def next_number(self, clinic_id: UUID) -> str:
        counter = await self._get_or_create_counter(clinic_id)
        value = dict(counter.value or {})
        prefix = value.get("prefix", DEFAULT_PREFIX)
        padding = int(value.get("padding", DEFAULT_PADDING))
        next_value = int(value.get("next", 1))

        patient_number = f"{prefix}{str(next_value).zfill(padding)}"

        value["next"] = next_value + 1
        counter.value = value
        await self.session.flush()

        return patient_number
