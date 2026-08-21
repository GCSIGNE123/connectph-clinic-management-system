"""Medicine Inventory Phase 3: a dedicated, role-targeted notification
system for expiry alerts. Deliberately NOT a reuse of `InternalMessage` -
that model is a strict 1:1 human-to-human DM (`sender_id`/`recipient_id`
both required, "read on conversation-open" semantics), with no concept of
"broadcast to every Receptionist in this clinic." Kept intentionally small
and focused rather than a general-purpose notification framework - only
what Phase 3 (and structurally, any future role-targeted system alert)
needs.

Per-user read state: `NotificationRecipient` uses a "row presence = read"
pattern rather than a single shared `read_at` on `Notification` itself -
marking read inserts exactly one `NotificationRecipient` row for
`(notification_id, user_id)`. A user who has never marked a given
notification read simply has no row, so two different Receptionists can
each read the SAME role-targeted `Notification` independently ("Receptionist
A can read an alert while Receptionist B still sees it as unread" - no
fan-out write is needed at creation time, only at read time, and only for
users who actually open it).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class NotificationType(str, enum.Enum):
    MEDICINE_EXPIRY_WARNING = "medicine_expiry_warning"
    MEDICINE_EXPIRED = "medicine_expired"


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    """A single system-generated alert, broadcast to every user in
    `target_role` for this clinic (Owner/Administrator additionally see
    every notification regardless of `target_role` - see
    `NotificationService.list_for_user` - so they are never a separate
    target_role themselves). `recipient_id` is an escape hatch for a
    future specific-user notification; Phase 3 never sets it."""

    __tablename__ = "notifications"

    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_role: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Notification id={self.id} type={self.type!r}>"


class NotificationRecipient(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """A per-user read receipt for a `Notification` - see module docstring."""

    __tablename__ = "notification_recipients"
    __table_args__ = (UniqueConstraint("notification_id", "user_id", name="uq_notification_recipient"),)

    notification_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NotificationRecipient notification_id={self.notification_id} user_id={self.user_id}>"
