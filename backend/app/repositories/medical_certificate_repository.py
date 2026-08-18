"""Repository for MedicalCertificate."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.medical_certificate import MedicalCertificate


class MedicalCertificateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _detail_options(self):
        return (selectinload(MedicalCertificate.doctor), selectinload(MedicalCertificate.patient))

    async def create(self, **fields) -> MedicalCertificate:
        certificate = MedicalCertificate(**fields)
        self.session.add(certificate)
        await self.session.flush()
        await self.session.refresh(certificate, attribute_names=["doctor", "patient"])
        return certificate

    async def get(self, certificate_id: UUID, clinic_id: UUID) -> MedicalCertificate | None:
        stmt = (
            select(MedicalCertificate)
            .where(
                MedicalCertificate.id == certificate_id,
                MedicalCertificate.clinic_id == clinic_id,
                MedicalCertificate.is_deleted.is_(False),
            )
            .options(*self._detail_options())
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_consultation(self, consultation_id: UUID, clinic_id: UUID) -> list[MedicalCertificate]:
        stmt = (
            select(MedicalCertificate)
            .where(
                MedicalCertificate.consultation_id == consultation_id,
                MedicalCertificate.clinic_id == clinic_id,
                MedicalCertificate.is_deleted.is_(False),
            )
            .options(*self._detail_options())
            .order_by(MedicalCertificate.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_visit(self, visit_id: UUID, clinic_id: UUID) -> list[MedicalCertificate]:
        stmt = (
            select(MedicalCertificate)
            .where(
                MedicalCertificate.visit_id == visit_id,
                MedicalCertificate.clinic_id == clinic_id,
                MedicalCertificate.is_deleted.is_(False),
            )
            .options(*self._detail_options())
            .order_by(MedicalCertificate.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_patient(self, patient_id: UUID, clinic_id: UUID) -> list[MedicalCertificate]:
        stmt = (
            select(MedicalCertificate)
            .where(
                MedicalCertificate.patient_id == patient_id,
                MedicalCertificate.clinic_id == clinic_id,
                MedicalCertificate.is_deleted.is_(False),
            )
            .options(*self._detail_options())
            .order_by(MedicalCertificate.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update(self, certificate: MedicalCertificate, **fields) -> MedicalCertificate:
        for key, value in fields.items():
            setattr(certificate, key, value)
        await self.session.flush()
        # `updated_at` has a server-side `onupdate`, so SQLAlchemy always
        # expires it after any UPDATE - a later synchronous attribute read
        # (e.g. Pydantic's `model_validate`) would otherwise trigger an
        # implicit lazy refresh that `MissingGreenlet`s under asyncio (same
        # class of bug already fixed in `QueueService`'s laboratory-order
        # linking - see that fix's comment for the full explanation).
        await self.session.refresh(certificate, attribute_names=["updated_at"])
        return certificate
