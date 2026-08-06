"""Repository for the Patient Portal auth model (Phase 18).

Deliberately separate from `UserRepository` (clinic staff) and
`PlatformAdminUserRepository` (Phase 15) - mirrors that precedent exactly.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.patient import Patient
from app.models.patient_account import PatientAccount
from app.repositories.base import BaseRepository


class PatientAccountRepository(BaseRepository[PatientAccount]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=PatientAccount)

    async def get_by_patient_id(self, patient_id: UUID) -> PatientAccount | None:
        result = await self.session.execute(
            select(PatientAccount).where(PatientAccount.patient_id == patient_id)
        )
        return result.scalar_one_or_none()

    async def get_by_identifier(self, identifier: str) -> tuple[PatientAccount, Patient] | None:
        """Look up a patient account by email OR mobile number (matched on the
        linked `Patient` row, not on `PatientAccount` itself - login
        identifiers live on the shared patient record, credentials on the
        account). Excludes soft-deleted/archived patients."""
        result = await self.session.execute(
            select(PatientAccount, Patient)
            .join(Patient, Patient.id == PatientAccount.patient_id)
            .where(
                Patient.is_deleted.is_(False),
                (Patient.email == identifier) | (Patient.mobile_number == identifier),
            )
        )
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

    async def get_with_patient(self, patient_account_id: UUID) -> tuple[PatientAccount, Patient] | None:
        result = await self.session.execute(
            select(PatientAccount, Patient)
            .join(Patient, Patient.id == PatientAccount.patient_id)
            .where(PatientAccount.id == patient_account_id)
        )
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]
