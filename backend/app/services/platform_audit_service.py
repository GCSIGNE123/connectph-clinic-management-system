"""Platform audit logging - writes to `platform_audit_logs`, distinct from the
per-clinic `audit_logs` table (`app.services.audit_service.AuditService`).

Every tenant/license/subscription/feature-flag/platform-admin-action write
in this phase calls `PlatformAuditService.log`.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_audit_log import PlatformAuditLog


class PlatformAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        *,
        actor_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: str | None = None,
        clinic_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> PlatformAuditLog:
        entry = PlatformAuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            clinic_id=clinic_id,
            log_metadata=metadata,
            created_at=datetime.now(UTC),
        )
        self.session.add(entry)
        await self.session.flush()
        return entry
