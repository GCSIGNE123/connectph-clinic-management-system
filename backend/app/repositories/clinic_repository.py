"""Repository for Clinic model."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinic import Clinic
from app.repositories.base import BaseRepository


class ClinicRepository(BaseRepository[Clinic]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Clinic)

    async def get_by_slug(self, slug: str) -> Clinic | None:
        stmt = select(Clinic).where(Clinic.slug == slug, Clinic.is_deleted.is_(False))
        result = await self.session.execute(stmt)
        return result.scalars().first()
