"""Internal staff-to-staff messaging (Phase 20, item 14).

Deliberately minimal per spec: a simple Receptionist <-> Doctor message
list, not a general chat system - no threads/conversations table, no
attachments, no group recipients, no read receipts beyond a single boolean
(`read_at` timestamp, null until read). `recipient_id` targets a specific
user (not a role) so the list/unread-count queries are simple `WHERE
recipient_id = :me` lookups, matching how a Receptionist picks a specific
Doctor (and vice versa) to message in the minimal send UI.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InternalMessage(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "internal_messages"

    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sender: Mapped["User"] = relationship(foreign_keys=[sender_id])  # noqa: F821
    recipient: Mapped["User"] = relationship(foreign_keys=[recipient_id])  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InternalMessage id={self.id} sender_id={self.sender_id} recipient_id={self.recipient_id}>"
