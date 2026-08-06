"""Appointment number generator, mirroring `OrderNumberGenerator`/
`PrescriptionNumberGenerator` (a `system_settings`-backed, date-scoped,
concurrency-safe JSONB counter). Format: `APT-YYYYMMDD-000001`.
"""

from app.services.clinical_number_generator import _DailyNumberGenerator
from sqlalchemy.ext.asyncio import AsyncSession


class AppointmentNumberGenerator(_DailyNumberGenerator):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, key_prefix="appointment_number_counter", number_prefix="APT")
