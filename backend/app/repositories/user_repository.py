"""Repository for User model."""

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=User)

    async def get_by_email(self, email: str, clinic_id: UUID | None = None) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.role))
            .where(User.email == email, User.is_deleted.is_(False))
        )
        if clinic_id is not None:
            stmt = stmt.where(User.clinic_id == clinic_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_username(self, username: str, clinic_id: UUID | None = None) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.role))
            .where(User.username == username, User.is_deleted.is_(False))
        )
        if clinic_id is not None:
            stmt = stmt.where(User.clinic_id == clinic_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_email_or_username(
        self, identifier: str, clinic_id: UUID | None = None
    ) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.role))
            .where(
                or_(User.email == identifier, User.username == identifier),
                User.is_deleted.is_(False),
            )
        )
        if clinic_id is not None:
            stmt = stmt.where(User.clinic_id == clinic_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_id(self, id_: UUID) -> User | None:
        stmt = select(User).options(selectinload(User.role)).where(User.id == id_)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.role))
            .where(User.id == id_, User.clinic_id == clinic_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def search(
        self,
        clinic_id: UUID,
        *,
        query: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """Search users within a clinic by name/email/username, with pagination.

        Returns (rows, total_count).
        """
        base_stmt = select(User).where(User.clinic_id == clinic_id, User.is_deleted.is_(False))
        count_stmt = select(func.count()).select_from(User).where(
            User.clinic_id == clinic_id, User.is_deleted.is_(False)
        )

        if query:
            like = f"%{query.lower()}%"
            search_filter = or_(
                func.lower(User.first_name).like(like),
                func.lower(User.last_name).like(like),
                func.lower(User.email).like(like),
                func.lower(User.username).like(like),
            )
            base_stmt = base_stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        base_stmt = (
            base_stmt.options(selectinload(User.role))
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        rows_result = await self.session.execute(base_stmt)
        count_result = await self.session.execute(count_stmt)
        return list(rows_result.scalars().all()), int(count_result.scalar_one())
