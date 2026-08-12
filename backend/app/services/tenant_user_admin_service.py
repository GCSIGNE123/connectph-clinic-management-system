"""Platform-admin operations on a tenant's own users: list, reset password,
lock/unlock, force-logout.

Reuses the existing `users`/`refresh_tokens` tables and account-lockout
fields added in Phase 2 (`UserStatus`, `failed_login_attempts`,
`locked_until`) rather than building a parallel mechanism - per the phase
spec's "reuse Phase 2's user-management service where the operation already
exists" guidance. This is intentionally a THIN, separate service (not
`UserService`) because `UserService.admin_reset_password` etc. require a
clinic `User` as the acting actor (for the per-clinic `audit_logs` table);
a platform admin is not a clinic `User`, so actions here are attributed to
the platform admin and recorded in `platform_audit_logs` instead.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User, UserStatus
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.services.platform_audit_service import PlatformAuditService


class TenantUserAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.refresh_token_repo = RefreshTokenRepository(session)
        self.audit = PlatformAuditService(session)

    async def list_tenant_users(self, clinic_id: UUID) -> list[User]:
        from sqlalchemy.orm import selectinload  # noqa: PLC0415

        result = await self.session.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.clinic_id == clinic_id, User.is_deleted.is_(False))
            .order_by(User.created_at)
        )
        return list(result.scalars().all())

    async def _get_user(self, clinic_id: UUID, user_id: UUID) -> User:
        result = await self.session.execute(
            select(User).where(User.id == user_id, User.clinic_id == clinic_id, User.is_deleted.is_(False))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant user not found")
        return user

    async def _get_user_with_role(self, clinic_id: UUID, user_id: UUID) -> User:
        """Same lookup as `_get_user`, but eager-loads `.role` - needed by
        `update_user`'s return value, which the router serializes into
        `TenantUserRead.role`. Async SQLAlchemy cannot lazy-load a
        relationship outside an explicit eager-load option, so skipping this
        would crash with a MissingGreenlet error on that field access."""
        from sqlalchemy.orm import selectinload  # noqa: PLC0415

        result = await self.session.execute(
            select(User)
            .options(selectinload(User.role))
            .where(User.id == user_id, User.clinic_id == clinic_id, User.is_deleted.is_(False))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant user not found")
        return user

    async def update_user(
        self,
        *,
        actor_id: UUID,
        clinic_id: UUID,
        user_id: UUID,
        email: str | None = None,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        role_id: UUID | None = None,
    ) -> User:
        user = await self._get_user(clinic_id, user_id)

        if email is not None and email != user.email:
            existing = await self.session.execute(
                select(User).where(
                    User.clinic_id == clinic_id, User.email == email, User.id != user_id, User.is_deleted.is_(False)
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use in this clinic")
            user.email = email

        if username is not None and username != user.username:
            existing = await self.session.execute(
                select(User).where(
                    User.clinic_id == clinic_id, User.username == username, User.id != user_id, User.is_deleted.is_(False)
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already in use in this clinic")
            user.username = username

        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if role_id is not None:
            user.role_id = role_id

        await self.audit.log(
            actor_id=actor_id, action="tenant_user.update", entity_type="user",
            entity_id=str(user_id), clinic_id=clinic_id,
            metadata={
                "fields": [
                    k for k, v in {
                        "email": email, "username": username, "first_name": first_name,
                        "last_name": last_name, "role_id": str(role_id) if role_id else None,
                    }.items() if v is not None
                ]
            },
        )
        await self.session.commit()
        return await self._get_user_with_role(clinic_id, user_id)

    async def delete_user(self, *, actor_id: UUID, clinic_id: UUID, user_id: UUID) -> None:
        user = await self._get_user(clinic_id, user_id)
        user.is_deleted = True
        await self.refresh_token_repo.revoke_all_for_user(user.id)
        await self.audit.log(
            actor_id=actor_id, action="tenant_user.delete", entity_type="user",
            entity_id=str(user_id), clinic_id=clinic_id,
        )
        await self.session.commit()

    async def reset_password(self, *, actor_id: UUID, clinic_id: UUID, user_id: UUID, new_password: str) -> None:
        user = await self._get_user(clinic_id, user_id)
        user.hashed_password = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE
        await self.refresh_token_repo.revoke_all_for_user(user.id)
        await self.audit.log(
            actor_id=actor_id, action="tenant_user.password_reset", entity_type="user",
            entity_id=str(user_id), clinic_id=clinic_id,
        )
        await self.session.commit()

    async def lock(self, *, actor_id: UUID, clinic_id: UUID, user_id: UUID) -> User:
        user = await self._get_user(clinic_id, user_id)
        user.status = UserStatus.LOCKED
        user.locked_until = None  # indefinite, platform-admin-imposed lock
        await self.refresh_token_repo.revoke_all_for_user(user.id)
        await self.audit.log(
            actor_id=actor_id, action="tenant_user.lock", entity_type="user", entity_id=str(user_id), clinic_id=clinic_id
        )
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def unlock(self, *, actor_id: UUID, clinic_id: UUID, user_id: UUID) -> User:
        user = await self._get_user(clinic_id, user_id)
        user.status = UserStatus.ACTIVE
        user.locked_until = None
        user.failed_login_attempts = 0
        await self.audit.log(
            actor_id=actor_id, action="tenant_user.unlock", entity_type="user", entity_id=str(user_id), clinic_id=clinic_id
        )
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def force_logout(self, *, actor_id: UUID, clinic_id: UUID, user_id: UUID) -> None:
        user = await self._get_user(clinic_id, user_id)
        await self.refresh_token_repo.revoke_all_for_user(user.id)
        await self.audit.log(
            actor_id=actor_id, action="tenant_user.force_logout", entity_type="user",
            entity_id=str(user_id), clinic_id=clinic_id,
        )
        await self.session.commit()
