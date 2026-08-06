"""Login/logout/refresh for Platform Administration Portal accounts.

Separate from `app.services.auth_service.AuthService` (clinic-user auth).
Issues tokens via `app.core.platform_admin_security`, never
`app.core.security.create_access_token`/`create_refresh_token`.
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.platform_admin_security import (
    PLATFORM_ADMIN_REFRESH_TOKEN_EXPIRE_DAYS,
    PlatformTokenType,
    create_platform_access_token,
    create_platform_refresh_token,
    decode_platform_token,
)
from app.core.security import TokenPayloadError, generate_secure_token, hash_token, verify_password
from app.models.platform_admin_user import PlatformAdminUser
from app.repositories.platform_admin_repository import PlatformAdminUserRepository, PlatformSessionRepository
from app.services.platform_audit_service import PlatformAuditService


class PlatformAuthResult:
    def __init__(self, *, access_token: str, refresh_token: str, admin: PlatformAdminUser) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.admin = admin


class PlatformAdminAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.admin_repo = PlatformAdminUserRepository(session)
        self.session_repo = PlatformSessionRepository(session)
        self.audit = PlatformAuditService(session)

    async def login(
        self, *, identifier: str, password: str, ip_address: str | None, user_agent: str | None
    ) -> PlatformAuthResult:
        admin = await self.admin_repo.get_by_email_or_username(identifier)
        if admin is None or not verify_password(password, admin.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if not admin.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin account is inactive")

        access_token = create_platform_access_token(platform_admin_id=admin.id, role=admin.role.value)
        raw_refresh = generate_secure_token()

        from app.models.platform_session import PlatformSession  # noqa: PLC0415

        now = datetime.now(UTC)
        record = PlatformSession(
            platform_admin_user_id=admin.id,
            token_hash=hash_token(raw_refresh),
            ip_address=ip_address,
            user_agent=user_agent,
            last_seen_at=now,
            expires_at=now + timedelta(days=PLATFORM_ADMIN_REFRESH_TOKEN_EXPIRE_DAYS),
        )
        self.session.add(record)

        admin.last_login_at = now
        await self.session.flush()

        await self.audit.log(
            actor_id=admin.id, action="platform_admin.login", entity_type="platform_admin_user", entity_id=str(admin.id)
        )
        await self.session.commit()

        refresh_token = create_platform_refresh_token(platform_admin_id=admin.id, role=admin.role.value)
        return PlatformAuthResult(access_token=access_token, refresh_token=refresh_token, admin=admin)

    async def refresh(self, raw_refresh_token: str) -> PlatformAuthResult:
        try:
            payload = decode_platform_token(raw_refresh_token, expected_type=PlatformTokenType.REFRESH)
        except TokenPayloadError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

        from uuid import UUID  # noqa: PLC0415

        admin = await self.admin_repo.get_by_id(UUID(payload["platform_admin_id"]))
        if admin is None or not admin.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Platform admin not found")

        access_token = create_platform_access_token(platform_admin_id=admin.id, role=admin.role.value)
        new_refresh = create_platform_refresh_token(platform_admin_id=admin.id, role=admin.role.value)
        return PlatformAuthResult(access_token=access_token, refresh_token=new_refresh, admin=admin)

    async def logout(self, admin: PlatformAdminUser) -> None:
        await self.audit.log(
            actor_id=admin.id, action="platform_admin.logout", entity_type="platform_admin_user", entity_id=str(admin.id)
        )
        await self.session.commit()
