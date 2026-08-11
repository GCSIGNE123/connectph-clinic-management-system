"""Repositories for TV display configs and announcements."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tv_announcement import TvAnnouncement
from app.models.tv_display_config import TvDisplayConfig
from app.models.tv_info_content import TvInfoContent
from app.repositories.base import BaseRepository


class TvDisplayConfigRepository(BaseRepository[TvDisplayConfig]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=TvDisplayConfig)

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> TvDisplayConfig | None:
        stmt = select(TvDisplayConfig).where(
            TvDisplayConfig.id == id_,
            TvDisplayConfig.clinic_id == clinic_id,
            TvDisplayConfig.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_public_slug(self, public_slug: str) -> TvDisplayConfig | None:
        """No clinic scoping here by design - the slug itself *is* the
        clinic-scoping mechanism for the unauthenticated public endpoint;
        see `services/tv_display_service.py::get_public_display_data`."""
        stmt = select(TvDisplayConfig).where(
            TvDisplayConfig.public_slug == public_slug,
            TvDisplayConfig.is_deleted.is_(False),
            TvDisplayConfig.is_public.is_(True),
            TvDisplayConfig.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_clinic(self, clinic_id: UUID, *, limit: int = 100, offset: int = 0) -> list[TvDisplayConfig]:
        stmt = (
            select(TvDisplayConfig)
            .where(TvDisplayConfig.clinic_id == clinic_id, TvDisplayConfig.is_deleted.is_(False))
            .order_by(TvDisplayConfig.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def slug_exists(self, public_slug: str) -> bool:
        stmt = select(TvDisplayConfig.id).where(TvDisplayConfig.public_slug == public_slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


class TvAnnouncementRepository(BaseRepository[TvAnnouncement]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=TvAnnouncement)

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> TvAnnouncement | None:
        stmt = select(TvAnnouncement).where(
            TvAnnouncement.id == id_, TvAnnouncement.clinic_id == clinic_id, TvAnnouncement.is_deleted.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_config(self, clinic_id: UUID, config_id: UUID) -> list[TvAnnouncement]:
        stmt = select(TvAnnouncement).where(
            TvAnnouncement.clinic_id == clinic_id,
            TvAnnouncement.is_deleted.is_(False),
            TvAnnouncement.tv_display_config_id == config_id,
        ).order_by(TvAnnouncement.display_order.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_display(
        self, clinic_id: UUID, config_id: UUID, today: date
    ) -> list[TvAnnouncement]:
        """Active announcements visible on a given display: clinic-wide
        (`tv_display_config_id IS NULL`) OR scoped to this exact display,
        filtered to the active date range (if set) and `is_active`."""
        stmt = select(TvAnnouncement).where(
            TvAnnouncement.clinic_id == clinic_id,
            TvAnnouncement.is_deleted.is_(False),
            TvAnnouncement.is_active.is_(True),
            (TvAnnouncement.tv_display_config_id.is_(None)) | (TvAnnouncement.tv_display_config_id == config_id),
        ).order_by(TvAnnouncement.display_order.asc())
        result = await self.session.execute(stmt)
        announcements = list(result.scalars().all())
        return [
            a for a in announcements
            if (a.starts_at is None or a.starts_at <= today) and (a.ends_at is None or a.ends_at >= today)
        ]


class TvInfoContentRepository(BaseRepository[TvInfoContent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=TvInfoContent)

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> TvInfoContent | None:
        stmt = select(TvInfoContent).where(
            TvInfoContent.id == id_, TvInfoContent.clinic_id == clinic_id, TvInfoContent.is_deleted.is_(False)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_clinic(self, clinic_id: UUID) -> list[TvInfoContent]:
        stmt = select(TvInfoContent).where(
            TvInfoContent.clinic_id == clinic_id, TvInfoContent.is_deleted.is_(False)
        ).order_by(TvInfoContent.display_order.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_clinic(self, clinic_id: UUID) -> list[TvInfoContent]:
        stmt = select(TvInfoContent).where(
            TvInfoContent.clinic_id == clinic_id,
            TvInfoContent.is_deleted.is_(False),
            TvInfoContent.is_active.is_(True),
        ).order_by(TvInfoContent.display_order.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
