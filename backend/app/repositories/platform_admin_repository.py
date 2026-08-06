"""Repositories for the platform-admin (cross-tenant) data model.

These repositories deliberately query WITHOUT any `clinic_id` filter where
appropriate (e.g. listing all clinics) - that is the entire point of this
phase's cross-tenant layer. They are only ever reachable from
`services/platform_admin_auth_service.py` and the other `platform_*`/
`tenant_management_service.py` services, which are in turn only reachable via
`get_current_platform_admin` (see `core/dependencies.py`). Regular
clinic-scoped repositories (e.g. `UserRepository`, `ClinicRepository` reads
used elsewhere) are completely untouched by this file.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_admin_user import PlatformAdminUser
from app.models.platform_session import PlatformSession
from app.repositories.base import BaseRepository


class PlatformAdminUserRepository(BaseRepository[PlatformAdminUser]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=PlatformAdminUser)

    async def get_by_email(self, email: str) -> PlatformAdminUser | None:
        result = await self.session.execute(select(PlatformAdminUser).where(PlatformAdminUser.email == email))
        return result.scalar_one_or_none()

    async def get_by_email_or_username(self, identifier: str) -> PlatformAdminUser | None:
        result = await self.session.execute(
            select(PlatformAdminUser).where(
                (PlatformAdminUser.email == identifier) | (PlatformAdminUser.username == identifier)
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PlatformAdminUser]:
        result = await self.session.execute(select(PlatformAdminUser).order_by(PlatformAdminUser.created_at))
        return list(result.scalars().all())


class PlatformSessionRepository(BaseRepository[PlatformSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=PlatformSession)

    async def get_by_token_hash(self, token_hash: str) -> PlatformSession | None:
        result = await self.session.execute(select(PlatformSession).where(PlatformSession.token_hash == token_hash))
        return result.scalar_one_or_none()

    async def list_active(self) -> list[PlatformSession]:
        result = await self.session.execute(
            select(PlatformSession)
            .where(PlatformSession.terminated_at.is_(None))
            .order_by(PlatformSession.last_seen_at.desc())
        )
        return list(result.scalars().all())

    async def terminate(self, session_row: PlatformSession, *, terminated_by: UUID) -> None:
        session_row.terminated_at = datetime.now(UTC)
        session_row.terminated_by = terminated_by
        await self.session.flush()
