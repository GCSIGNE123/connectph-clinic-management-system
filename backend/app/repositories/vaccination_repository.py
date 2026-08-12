"""Repository for Vaccination Administration records (Post-RC1)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.vaccination_administration import VaccinationAdministration, VaccinationStatus


def _options():
    return (
        selectinload(VaccinationAdministration.order),
        selectinload(VaccinationAdministration.patient),
        selectinload(VaccinationAdministration.doctor),
    )


class VaccinationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, **fields) -> VaccinationAdministration:
        record = VaccinationAdministration(**fields)
        self.session.add(record)
        await self.session.flush()
        await self.session.refresh(record, attribute_names=["order", "patient", "doctor"])
        return record

    async def get_by_id(self, vaccination_id: UUID, clinic_id: UUID) -> VaccinationAdministration | None:
        stmt = (
            select(VaccinationAdministration)
            .where(
                VaccinationAdministration.id == vaccination_id,
                VaccinationAdministration.clinic_id == clinic_id,
                VaccinationAdministration.is_deleted.is_(False),
            )
            .options(*_options())
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_order_id(self, order_id: UUID, clinic_id: UUID) -> VaccinationAdministration | None:
        stmt = (
            select(VaccinationAdministration)
            .where(
                VaccinationAdministration.order_id == order_id,
                VaccinationAdministration.clinic_id == clinic_id,
                VaccinationAdministration.is_deleted.is_(False),
            )
            .options(*_options())
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_clinic(self, clinic_id: UUID, *, status: VaccinationStatus | None = None) -> list[VaccinationAdministration]:
        filters = [VaccinationAdministration.clinic_id == clinic_id, VaccinationAdministration.is_deleted.is_(False)]
        if status is not None:
            filters.append(VaccinationAdministration.status == status)
        stmt = (
            select(VaccinationAdministration)
            .where(*filters)
            .options(*_options())
            .order_by(VaccinationAdministration.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_patient(self, patient_id: UUID, clinic_id: UUID) -> list[VaccinationAdministration]:
        stmt = (
            select(VaccinationAdministration)
            .where(
                VaccinationAdministration.patient_id == patient_id,
                VaccinationAdministration.clinic_id == clinic_id,
                VaccinationAdministration.is_deleted.is_(False),
            )
            .options(*_options())
            .order_by(VaccinationAdministration.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update(self, record: VaccinationAdministration, **fields) -> VaccinationAdministration:
        for key, value in fields.items():
            setattr(record, key, value)
        await self.session.flush()
        return record
