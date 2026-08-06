"""Internal staff messaging service (Phase 20, item 14).

Deliberately minimal - direct queries against `InternalMessage`, no separate
repository layer (the query shapes are simple enough that adding one would
just be indirection). Every query is clinic-scoped and every mutation is
scoped to the caller (`current_user.id`) as sender or recipient - a user can
only ever read their own conversations and mark their own received messages
as read, mirroring the tenant/self-scoping pattern used everywhere else in
this codebase (e.g. Patient Portal's `current.id`-scoped queries).
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.internal_message import InternalMessage
from app.models.user import User
from app.schemas.internal_message import InternalMessageRead


def _full_name(user: User | None) -> str | None:
    if user is None:
        return None
    parts = [user.first_name, user.middle_name, user.last_name]
    return " ".join(p for p in parts if p)


class InternalMessageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _require_recipient(self, recipient_id: UUID, clinic_id: UUID) -> User:
        recipient = await self.session.get(User, recipient_id)
        if recipient is None or recipient.clinic_id != clinic_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found in this clinic.")
        return recipient

    def _to_read(self, msg: InternalMessage) -> InternalMessageRead:
        return InternalMessageRead(
            id=msg.id,
            sender_id=msg.sender_id,
            sender_name=_full_name(msg.sender),
            recipient_id=msg.recipient_id,
            recipient_name=_full_name(msg.recipient),
            body=msg.body,
            read_at=msg.read_at,
            created_at=msg.created_at,
        )

    async def send(self, *, clinic_id: UUID, sender_id: UUID, recipient_id: UUID, body: str) -> InternalMessageRead:
        await self._require_recipient(recipient_id, clinic_id)
        if recipient_id == sender_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot message yourself.")
        msg = InternalMessage(clinic_id=clinic_id, sender_id=sender_id, recipient_id=recipient_id, body=body)
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg, attribute_names=["sender", "recipient"])
        return self._to_read(msg)

    async def list_conversation(
        self, *, clinic_id: UUID, current_user_id: UUID, other_user_id: UUID, limit: int = 100, offset: int = 0
    ) -> tuple[list[InternalMessageRead], int, int]:
        """Every message between `current_user_id` and `other_user_id`,
        oldest first (chat-log order), plus the current user's total unread
        count across ALL conversations (for a simple "you have new
        messages" indicator)."""
        base_filter = (
            (InternalMessage.clinic_id == clinic_id)
            & or_(
                (InternalMessage.sender_id == current_user_id) & (InternalMessage.recipient_id == other_user_id),
                (InternalMessage.sender_id == other_user_id) & (InternalMessage.recipient_id == current_user_id),
            )
        )
        stmt = (
            select(InternalMessage)
            .where(base_filter)
            .options(selectinload(InternalMessage.sender), selectinload(InternalMessage.recipient))
            .order_by(InternalMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        messages = list(result.scalars().all())

        count_stmt = select(func.count()).select_from(InternalMessage).where(base_filter)
        total = (await self.session.execute(count_stmt)).scalar_one()

        unread_stmt = select(func.count()).select_from(InternalMessage).where(
            (InternalMessage.clinic_id == clinic_id)
            & (InternalMessage.recipient_id == current_user_id)
            & (InternalMessage.read_at.is_(None))
        )
        unread_count = (await self.session.execute(unread_stmt)).scalar_one()

        # Mark the other party's messages to me as read, now that I've
        # fetched this conversation (simple "opened it, so it's read" model
        # - no per-message read toggle in the minimal UI).
        now = datetime.now(UTC)
        to_mark = [m for m in messages if m.recipient_id == current_user_id and m.read_at is None]
        for m in to_mark:
            m.read_at = now
        if to_mark:
            await self.session.commit()
            unread_count = max(0, unread_count - len(to_mark))

        return [self._to_read(m) for m in messages], total, unread_count

    async def unread_count(self, *, clinic_id: UUID, current_user_id: UUID) -> int:
        stmt = select(func.count()).select_from(InternalMessage).where(
            (InternalMessage.clinic_id == clinic_id)
            & (InternalMessage.recipient_id == current_user_id)
            & (InternalMessage.read_at.is_(None))
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def unread_by_conversation(self, *, clinic_id: UUID, current_user_id: UUID) -> list[dict]:
        """Breaks the single clinic-wide `unread_count` total down per
        conversation partner (item 6), so the frontend can show "which
        conversation(s) have unread messages" and mark only the opened one
        read without touching the others' indicators - the underlying
        `read_at` column is already per-message/per-recipient, so opening
        one conversation (`list_conversation`) only ever updates rows where
        `sender_id == other_user_id`, leaving every other partner's unread
        rows untouched."""
        unread_stmt = (
            select(
                InternalMessage.sender_id,
                func.count().label("unread_count"),
                func.max(InternalMessage.created_at).label("last_message_at"),
            )
            .where(
                (InternalMessage.clinic_id == clinic_id)
                & (InternalMessage.recipient_id == current_user_id)
                & (InternalMessage.read_at.is_(None))
            )
            .group_by(InternalMessage.sender_id)
        )
        rows = (await self.session.execute(unread_stmt)).all()
        result = []
        for row in rows:
            sender = await self.session.get(User, row.sender_id)
            result.append(
                {
                    "other_user_id": row.sender_id,
                    "other_user_name": _full_name(sender),
                    "unread_count": row.unread_count,
                    "last_message_at": row.last_message_at,
                }
            )
        result.sort(key=lambda r: r["last_message_at"], reverse=True)
        return result
