"""Repository for Phase 12 - Owner Dashboard & Reports.

Cross-cutting aggregation that does not naturally belong to any single
existing repository (the real-time Activity Feed merges rows from three
different existing tables; Owner Alerts are live threshold checks against
existing operational data). Everything else that already had a natural home
(revenue -> `InvoiceRepository`, queue waits -> `QueueRepository`, lab
turnaround -> `LaboratoryRepository`, appointments -> `AppointmentRepository`,
patient census -> `VisitRepository`/`PatientRepository`) was added directly
to those repositories instead of duplicated here - see each file's "Phase 12"
section.

No new tables. Every query here reads from `audit_logs`, `queue_status_history`,
`visit_timeline_events`, `queues`, and `invoices` - all of which already
exist from earlier phases.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.queue import Queue, QueueStatus, QueueStatusHistory


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Real-time Activity Feed ---
    # Merges three already-recorded event streams (visit timeline events are
    # read via `VisitRepository.recent_timeline_events`, called from the
    # service layer alongside these two) - queried and formatted, not a new
    # event-logging mechanism.

    async def recent_audit_logs(self, clinic_id: UUID, limit: int = 50) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.clinic_id == clinic_id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def recent_queue_status_changes(self, clinic_id: UUID, limit: int = 50) -> list[QueueStatusHistory]:
        stmt = (
            select(QueueStatusHistory)
            .where(QueueStatusHistory.clinic_id == clinic_id)
            .order_by(QueueStatusHistory.changed_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    # --- Owner Alerts (live threshold checks, not persisted notifications) ---

    async def current_waiting_count(self, clinic_id: UUID, today) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Queue).where(
            Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False),
            Queue.queue_date == today, Queue.status == QueueStatus.WAITING,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def longest_current_wait_seconds(self, clinic_id: UUID, today, now: datetime) -> float | None:
        from sqlalchemy import func

        stmt = select(func.min(Queue.created_at)).where(
            Queue.clinic_id == clinic_id, Queue.is_deleted.is_(False),
            Queue.queue_date == today, Queue.status == QueueStatus.WAITING,
        )
        oldest = (await self.session.execute(stmt)).scalar_one_or_none()
        if oldest is None:
            return None
        return (now - oldest).total_seconds()
