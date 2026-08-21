"""Repository for `Notification`/`NotificationRecipient` (Phase 3)."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationRecipient
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Notification)

    def _visibility_filter(self, clinic_id: UUID, *, role_name: str | None, user_id: UUID, is_privileged: bool):
        base = [Notification.clinic_id == clinic_id]
        if is_privileged:
            # Owner/Administrator see every notification in the clinic
            # regardless of target_role - see NotificationService docstring.
            return base
        role_or_recipient = [Notification.recipient_id == user_id]
        if role_name:
            role_or_recipient.append(Notification.target_role == role_name)
        base.append(or_(*role_or_recipient))
        return base

    async def list_visible(
        self, clinic_id: UUID, *, role_name: str | None, user_id: UUID, is_privileged: bool, limit: int = 50, offset: int = 0
    ) -> tuple[list[Notification], int]:
        filters = self._visibility_filter(clinic_id, role_name=role_name, user_id=user_id, is_privileged=is_privileged)

        count_stmt = select(func.count()).select_from(Notification).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = select(Notification).where(and_(*filters)).order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    async def count_unread(self, clinic_id: UUID, *, role_name: str | None, user_id: UUID, is_privileged: bool) -> int:
        filters = self._visibility_filter(clinic_id, role_name=role_name, user_id=user_id, is_privileged=is_privileged)
        read_subquery = (
            select(NotificationRecipient.notification_id)
            .where(NotificationRecipient.notification_id == Notification.id, NotificationRecipient.user_id == user_id)
        )
        stmt = select(func.count()).select_from(Notification).where(and_(*filters), ~read_subquery.exists())
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_read_ids(self, notification_ids: list[UUID], user_id: UUID) -> set[UUID]:
        if not notification_ids:
            return set()
        stmt = select(NotificationRecipient.notification_id).where(
            NotificationRecipient.notification_id.in_(notification_ids), NotificationRecipient.user_id == user_id
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return set(rows)

    async def mark_read(self, notification_id: UUID, *, user_id: UUID, clinic_id: UUID) -> None:
        # ON CONFLICT DO NOTHING: idempotent - marking an already-read
        # notification read again is a harmless no-op, same
        # insert-and-ignore-duplicate pattern as `VisitNumberGenerator`.
        stmt = (
            pg_insert(NotificationRecipient)
            .values(clinic_id=clinic_id, notification_id=notification_id, user_id=user_id)
            .on_conflict_do_nothing(index_elements=["notification_id", "user_id"])
        )
        await self.session.execute(stmt)
