"""Audit logging service - writes audit trail rows for security-relevant events."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditService:
    """Writes append-only audit log entries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log_event(
        self,
        *,
        clinic_id: UUID,
        action: str,
        user_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            clinic_id=clinic_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=metadata,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def log_login_success(
        self, *, clinic_id: UUID, user_id: UUID, ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        return await self.log_event(
            clinic_id=clinic_id,
            user_id=user_id,
            action="auth.login.success",
            entity_type="user",
            entity_id=str(user_id),
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_login_failure(
        self, *, clinic_id: UUID | None, email: str, ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog | None:
        if clinic_id is None:
            # Without a resolved tenant we cannot satisfy the clinic_id FK; skip persisting.
            return None
        return await self.log_event(
            clinic_id=clinic_id,
            action="auth.login.failure",
            entity_type="user",
            entity_id=email,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"email": email},
        )
