"""Visit editing lock (Phase 7 - Doctor Workspace).

When a doctor opens a Visit for consultation, `POST
/doctor-workspace/visits/{id}/open` acquires a `VisitLock` row. While the
lock is held (`released_at IS NULL`) by a *different* user, other users may
still view the visit but cannot perform doctor actions on it - the API
returns the lock holder's identity so the frontend can render a "Currently
being edited by Dr. ___" banner and disable action buttons.

Release strategy (documented decision - see `doctor_workspace_service.py`):
a lock is released in three ways, whichever happens first:
1. Explicit release (`POST .../release-lock`, e.g. the doctor navigates away).
2. The underlying Visit reaches a terminal status (`Completed`, `Cancelled`,
   `NoShow`) - `complete_consultation`/`cancel_visit`/`mark_no_show` release
   any open lock as a side effect.
3. Heartbeat expiry - `open_visit` treats a lock whose `locked_at` is older
   than `LOCK_TTL_MINUTES` (see service) as stale and lets a new caller take
   it over, so a crashed tab / closed browser cannot wedge a visit forever.
   The frontend is expected to re-call `open` periodically as a heartbeat
   while the visit viewer stays mounted (see `use-doctor-actions.ts`).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VisitLock(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "visit_locks"

    visit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    locked_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    visit: Mapped["Visit"] = relationship()
    locked_by_user: Mapped["User"] = relationship()

    __table_args__ = (
        # Only one *active* lock row is meaningful per visit at a time; we
        # keep history (released rows) instead of deleting, so this is a
        # partial-like guard enforced in the service layer (an active-only
        # unique index would need a WHERE clause migration extension - the
        # service always checks for an existing un-released row first).
        UniqueConstraint("visit_id", "locked_at", name="uq_visit_lock_visit_locked_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VisitLock id={self.id} visit_id={self.visit_id} released={self.released_at is not None}>"
