"""Phase 3 notification service: role-scoped listing + per-user read state.

Visibility rule: Owner/Administrator see every notification in their clinic
regardless of `target_role` (a superset view - "Owner/Administrator should
also be able to see them" per spec, without needing a separate Notification
row per privileged role). Every other role sees only notifications whose
`target_role` matches their own role name, or whose `recipient_id` is them
specifically."""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository

PRIVILEGED_ROLES = {"Owner", "Administrator"}


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = NotificationRepository(session)

    @staticmethod
    def _role_context(user: User) -> tuple[str | None, bool]:
        role_name = user.role.name if user.role is not None else None
        return role_name, role_name in PRIVILEGED_ROLES

    async def create_role_notification(
        self, *, clinic_id: UUID, target_role: str, type_: str, title: str, body: str,
        entity_type: str | None = None, entity_id: UUID | None = None,
    ) -> Notification:
        notification = Notification(
            clinic_id=clinic_id, type=type_, title=title, body=body, target_role=target_role,
            entity_type=entity_type, entity_id=entity_id,
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def list_for_user(self, *, clinic_id: UUID, user: User, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        role_name, is_privileged = self._role_context(user)
        notifications, total = await self.repo.list_visible(
            clinic_id, role_name=role_name, user_id=user.id, is_privileged=is_privileged, limit=limit, offset=offset
        )
        read_ids = await self.repo.get_read_ids([n.id for n in notifications], user.id)
        items = [
            {
                "id": n.id, "clinic_id": n.clinic_id, "type": n.type, "title": n.title, "body": n.body,
                "entity_type": n.entity_type, "entity_id": n.entity_id, "created_at": n.created_at,
                "is_read": n.id in read_ids,
            }
            for n in notifications
        ]
        return items, total

    async def unread_count(self, *, clinic_id: UUID, user: User) -> int:
        role_name, is_privileged = self._role_context(user)
        return await self.repo.count_unread(clinic_id, role_name=role_name, user_id=user.id, is_privileged=is_privileged)

    async def _get_visible_or_404(self, notification_id: UUID, *, clinic_id: UUID, user: User) -> Notification:
        notification = await self.repo.get_by_id_and_clinic(notification_id, clinic_id)
        if notification is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        role_name, is_privileged = self._role_context(user)
        if not is_privileged and notification.target_role != role_name and notification.recipient_id != user.id:
            # Same "don't leak existence of another tenant's/role's row"
            # posture as every other cross-tenant guard in this codebase -
            # 404, not 403, so a user can't distinguish "not mine" from
            # "doesn't exist".
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
        return notification

    async def mark_read(self, notification_id: UUID, *, clinic_id: UUID, user: User) -> None:
        notification = await self._get_visible_or_404(notification_id, clinic_id=clinic_id, user=user)
        await self.repo.mark_read(notification.id, user_id=user.id, clinic_id=clinic_id)
        await self.session.commit()

    async def mark_all_read(self, *, clinic_id: UUID, user: User) -> int:
        role_name, is_privileged = self._role_context(user)
        notifications, _total = await self.repo.list_visible(
            clinic_id, role_name=role_name, user_id=user.id, is_privileged=is_privileged, limit=1000, offset=0
        )
        read_ids = await self.repo.get_read_ids([n.id for n in notifications], user.id)
        unread = [n for n in notifications if n.id not in read_ids]
        for notification in unread:
            await self.repo.mark_read(notification.id, user_id=user.id, clinic_id=clinic_id)
        await self.session.commit()
        return len(unread)
