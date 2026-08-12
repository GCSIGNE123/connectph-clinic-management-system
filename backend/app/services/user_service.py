"""User management service: create/update/disable/enable/search/admin-reset-password.

All operations are tenant-scoped (clinic_id) and write an audit log entry.
"""

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User, UserStatus
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import ChangeOwnPasswordRequest, UpdateOwnProfileRequest
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import AuditService


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.refresh_token_repo = RefreshTokenRepository(session)
        self.audit_service = AuditService(session)

    async def _ensure_unique(self, *, clinic_id: UUID, email: str, username: str) -> None:
        existing_email = await self.user_repo.get_by_email(email, clinic_id=clinic_id)
        if existing_email is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
        existing_username = await self.user_repo.get_by_username(username, clinic_id=clinic_id)
        if existing_username is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already in use")

    async def create_user(
        self, payload: UserCreate, *, clinic_id: UUID, actor: User
    ) -> User:
        await self._ensure_unique(clinic_id=clinic_id, email=payload.email, username=payload.username)

        user = await self.user_repo.create(
            clinic_id=clinic_id,
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(payload.password),
            first_name=payload.first_name,
            middle_name=payload.middle_name,
            last_name=payload.last_name,
            mobile_number=payload.mobile_number,
            role_id=payload.role_id,
            branch_id=payload.branch_id,
        )
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="user.created",
            entity_type="user", entity_id=str(user.id),
        )
        await self.session.commit()
        return await self.user_repo.get_by_id_and_clinic(user.id, clinic_id)

    async def update_user(
        self, user_id: UUID, payload: UserUpdate, *, clinic_id: UUID, actor: User
    ) -> User:
        user = await self.user_repo.get_by_id_and_clinic(user_id, clinic_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        updates = payload.model_dump(exclude_unset=True)
        user = await self.user_repo.update(user, **updates)
        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="user.updated",
            entity_type="user", entity_id=str(user_id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.user_repo.get_by_id_and_clinic(user.id, clinic_id)

    async def update_own_profile(self, payload: UpdateOwnProfileRequest, *, actor: User) -> User:
        """Self-service profile update (name/mobile number only - see
        `UpdateOwnProfileRequest`'s own docstring for why role_id/branch_id
        aren't reachable this way). No role-management dependency gates this
        - any authenticated user may update their own name/mobile number."""
        updates = payload.model_dump(exclude_unset=True)
        user = await self.user_repo.update(actor, **updates)
        await self.audit_service.log_event(
            clinic_id=actor.clinic_id, user_id=actor.id, action="user.updated_own_profile",
            entity_type="user", entity_id=str(actor.id), metadata={"fields": list(updates.keys())},
        )
        await self.session.commit()
        return await self.user_repo.get_by_id_and_clinic(user.id, actor.clinic_id)

    async def change_own_password(self, payload: ChangeOwnPasswordRequest, *, actor: User) -> None:
        if not verify_password(payload.current_password, actor.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        actor.hashed_password = hash_password(payload.new_password)
        await self.session.flush()
        # Revokes every refresh token for this user (same as
        # `admin_reset_password`) - a changed password should force a fresh
        # login everywhere, not just where it was changed. The short-lived
        # access token already in this request's Authorization header stays
        # valid until it naturally expires, but the next `/auth/refresh`
        # anywhere (including this tab) will fail and require re-login.
        await self.refresh_token_repo.revoke_all_for_user(actor.id)

        await self.audit_service.log_event(
            clinic_id=actor.clinic_id, user_id=actor.id, action="user.changed_own_password",
            entity_type="user", entity_id=str(actor.id),
        )
        await self.session.commit()

    async def disable_user(self, user_id: UUID, *, clinic_id: UUID, actor: User) -> User:
        user = await self.user_repo.get_by_id_and_clinic(user_id, clinic_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.is_active = False
        user.status = UserStatus.DISABLED
        await self.session.flush()
        await self.refresh_token_repo.revoke_all_for_user(user.id)

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="user.disabled",
            entity_type="user", entity_id=str(user_id),
        )
        await self.session.commit()
        return await self.user_repo.get_by_id_and_clinic(user.id, clinic_id)

    async def enable_user(self, user_id: UUID, *, clinic_id: UUID, actor: User) -> User:
        user = await self.user_repo.get_by_id_and_clinic(user_id, clinic_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.is_active = True
        user.status = UserStatus.ACTIVE
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="user.enabled",
            entity_type="user", entity_id=str(user_id),
        )
        await self.session.commit()
        return await self.user_repo.get_by_id_and_clinic(user.id, clinic_id)

    async def admin_reset_password(
        self, user_id: UUID, new_password: str, *, clinic_id: UUID, actor: User
    ) -> None:
        user = await self.user_repo.get_by_id_and_clinic(user_id, clinic_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user.hashed_password = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE
        await self.session.flush()
        await self.refresh_token_repo.revoke_all_for_user(user.id)

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="user.password_reset_by_admin",
            entity_type="user", entity_id=str(user_id),
        )
        await self.session.commit()

    async def search_users(
        self, *, clinic_id: UUID, query: str | None, limit: int, offset: int
    ) -> tuple[list[User], int]:
        return await self.user_repo.search(clinic_id, query=query, limit=limit, offset=offset)
