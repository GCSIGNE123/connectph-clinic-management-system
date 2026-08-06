"""Authentication service: login, logout, refresh, password reset, email verification.

Access tokens are short-lived JWTs (app.core.security). Refresh tokens are
opaque random strings, stored hashed in the `refresh_tokens` table so they can
be looked up, rotated, and revoked (JWT-based refresh tokens cannot be revoked
without an additional denylist, so we use the simpler, revocable, opaque
approach here per the phase-2 auth spec).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    generate_secure_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.role import Role, RoleName
from app.models.user import User, UserStatus
from app.repositories.clinic_repository import ClinicRepository
from app.repositories.email_verification_token_repository import EmailVerificationTokenRepository
from app.repositories.password_reset_token_repository import PasswordResetTokenRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.audit_service import AuditService


class AuthResult:
    """Bundle of the access token (JWT) plus the raw (unhashed) refresh token.

    The raw refresh token is only ever returned here, at issuance time; only
    its hash is persisted. Callers (the API layer) are responsible for placing
    it in an httpOnly cookie rather than returning it in a JSON body.
    """

    def __init__(self, *, access_token: str, refresh_token: str, user: User) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.user = user


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repo = UserRepository(session)
        self.clinic_repo = ClinicRepository(session)
        self.refresh_token_repo = RefreshTokenRepository(session)
        self.password_reset_repo = PasswordResetTokenRepository(session)
        self.email_verification_repo = EmailVerificationTokenRepository(session)
        self.audit_service = AuditService(session)

    # --- token issuance -------------------------------------------------

    def _create_access_token_for(self, user: User) -> str:
        role_name = user.role.name if user.role is not None else None
        return create_access_token(user_id=user.id, clinic_id=user.clinic_id, role=role_name)

    async def _issue_session(
        self,
        user: User,
        *,
        remember_me: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthResult:
        access_token = self._create_access_token_for(user)

        raw_refresh_token = generate_secure_token()
        days = (
            settings.REFRESH_TOKEN_EXPIRE_DAYS_REMEMBER_ME
            if remember_me
            else settings.REFRESH_TOKEN_EXPIRE_DAYS
        )
        expires_at = datetime.now(UTC) + timedelta(days=days)

        await self.refresh_token_repo.create(
            user_id=user.id,
            token_hash=hash_token(raw_refresh_token),
            expires_at=expires_at,
            remember_me=remember_me,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return AuthResult(access_token=access_token, refresh_token=raw_refresh_token, user=user)

    # --- login / lockout -------------------------------------------------

    async def login(
        self,
        payload: LoginRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuthResult:
        clinic_id: UUID | None = None
        if payload.clinic_slug:
            clinic = await self.clinic_repo.get_by_slug(payload.clinic_slug)
            clinic_id = clinic.id if clinic else None

        user = await self.user_repo.get_by_email_or_username(payload.email_or_username, clinic_id=clinic_id)

        if user is None:
            await self.audit_service.log_login_failure(
                clinic_id=clinic_id, email=payload.email_or_username,
                ip_address=ip_address, user_agent=user_agent,
            )
            await self.session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # Phase 15: a tenant suspended by a Platform Administrator blocks all
        # logins for that clinic's users, regardless of individual account
        # status. Archived clinics are blocked too (Suspended/Archived are the
        # only two non-Active clinic-level states).
        clinic = await self.clinic_repo.get_by_id(user.clinic_id)
        if clinic is not None and clinic.status in ("Suspended", "Archived"):
            await self.audit_service.log_event(
                clinic_id=user.clinic_id, user_id=user.id, action="auth.login.blocked_tenant_suspended",
                entity_type="user", entity_id=str(user.id),
                ip_address=ip_address, user_agent=user_agent,
            )
            await self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This clinic's account has been suspended. Please contact CONNECT.PH support.",
            )

        # Lockout check.
        now = datetime.now(UTC)
        locked_until = user.locked_until
        if locked_until is not None and locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=UTC)
        if locked_until is not None and locked_until > now:
            await self.audit_service.log_event(
                clinic_id=user.clinic_id, user_id=user.id, action="auth.login.blocked_locked",
                entity_type="user", entity_id=str(user.id),
                ip_address=ip_address, user_agent=user_agent,
            )
            await self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account is temporarily locked due to too many failed login attempts.",
            )

        if not verify_password(payload.password, user.hashed_password):
            user.failed_login_attempts += 1
            locked_now = False
            if user.failed_login_attempts >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                user.status = UserStatus.LOCKED
                locked_now = True
            await self.session.flush()

            await self.audit_service.log_login_failure(
                clinic_id=user.clinic_id, email=payload.email_or_username,
                ip_address=ip_address, user_agent=user_agent,
            )
            if locked_now:
                await self.audit_service.log_event(
                    clinic_id=user.clinic_id, user_id=user.id, action="auth.account.locked",
                    entity_type="user", entity_id=str(user.id),
                    ip_address=ip_address, user_agent=user_agent,
                )
            await self.session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if not user.is_active or user.status == UserStatus.DISABLED:
            await self.session.commit()
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled")

        # Successful login: reset lockout state.
        user.failed_login_attempts = 0
        user.locked_until = None
        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE
        await self.session.flush()

        await self.audit_service.log_login_success(
            clinic_id=user.clinic_id, user_id=user.id, ip_address=ip_address, user_agent=user_agent
        )
        result = await self._issue_session(
            user, remember_me=payload.remember_me, ip_address=ip_address, user_agent=user_agent
        )
        await self.session.commit()
        return result

    async def register(self, payload: RegisterRequest) -> AuthResult:
        existing_clinic = await self.clinic_repo.get_by_slug(payload.clinic_slug)
        if existing_clinic is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Clinic slug already in use")

        clinic = await self.clinic_repo.create(name=payload.clinic_name, slug=payload.clinic_slug)

        owner_role_stmt = select(Role).where(Role.name == RoleName.OWNER.value)
        result = await self.session.execute(owner_role_stmt)
        owner_role = result.scalar_one_or_none()
        if owner_role is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Owner role is not seeded; run migrations before registering.",
            )

        user = await self.user_repo.create(
            clinic_id=clinic.id,
            email=payload.email,
            username=payload.username,
            hashed_password=hash_password(payload.password),
            first_name=payload.first_name,
            last_name=payload.last_name,
            role_id=owner_role.id,
        )
        user.role = owner_role
        await self.session.commit()

        # TODO: send email verification link via SMTP (see request_email_verification).
        return await self._issue_session(user)

    # --- refresh / logout -------------------------------------------------

    async def refresh(
        self, raw_refresh_token: str, *, ip_address: str | None = None, user_agent: str | None = None
    ) -> AuthResult:
        token_hash = hash_token(raw_refresh_token)
        token_record = await self.refresh_token_repo.get_by_token_hash(token_hash)
        if token_record is None or not self.refresh_token_repo.is_valid(token_record):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

        user = await self.user_repo.get_by_id(token_record.user_id)
        if user is None or user.is_deleted or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

        # Rotate: revoke the old token, issue a new pair.
        await self.refresh_token_repo.revoke(token_record)
        result = await self._issue_session(
            user, remember_me=token_record.remember_me, ip_address=ip_address, user_agent=user_agent
        )
        await self.session.commit()
        return result

    async def logout(self, raw_refresh_token: str | None, *, user_id: UUID | None = None) -> None:
        if raw_refresh_token:
            token_hash = hash_token(raw_refresh_token)
            token_record = await self.refresh_token_repo.get_by_token_hash(token_hash)
            if token_record is not None and token_record.revoked_at is None:
                await self.refresh_token_repo.revoke(token_record)
                owner = await self.user_repo.get_by_id(token_record.user_id)
                if owner is not None:
                    await self.audit_service.log_event(
                        clinic_id=owner.clinic_id,
                        user_id=owner.id,
                        action="auth.logout",
                        entity_type="user",
                        entity_id=str(owner.id),
                    )
        await self.session.commit()

    async def logout_all_sessions(self, user_id: UUID, *, clinic_id: UUID | None = None) -> None:
        await self.refresh_token_repo.revoke_all_for_user(user_id)
        if clinic_id is not None:
            await self.audit_service.log_event(
                clinic_id=clinic_id, user_id=user_id, action="auth.logout_all_sessions",
                entity_type="user", entity_id=str(user_id),
            )
        await self.session.commit()

    # --- password reset -------------------------------------------------

    async def forgot_password(self, email: str) -> None:
        """Generates a reset token if the email exists. Always returns success generically."""
        user = await self.user_repo.get_by_email(email)
        if user is None:
            return None

        raw_token = generate_secure_token()
        expires_at = datetime.now(UTC) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        await self.password_reset_repo.create(
            user_id=user.id, token_hash=hash_token(raw_token), expires_at=expires_at
        )
        await self.audit_service.log_event(
            clinic_id=user.clinic_id, user_id=user.id, action="auth.password_reset.requested",
            entity_type="user", entity_id=str(user.id),
        )
        await self.session.commit()

        # TODO: send `raw_token` to the user via SMTP as a reset link
        # (e.g. https://app.connect.ph/reset-password?token=<raw_token>).
        # Never log or persist the raw token itself - only its hash is stored above.
        return None

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        token_hash = hash_token(raw_token)
        token_record = await self.password_reset_repo.get_by_token_hash(token_hash)
        if token_record is None or not self.password_reset_repo.is_valid(token_record):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        user = await self.user_repo.get_by_id(token_record.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        user.hashed_password = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE
        token_record.used_at = datetime.now(UTC)
        await self.session.flush()

        await self.refresh_token_repo.revoke_all_for_user(user.id)
        await self.audit_service.log_event(
            clinic_id=user.clinic_id, user_id=user.id, action="auth.password_reset.completed",
            entity_type="user", entity_id=str(user.id),
        )
        await self.session.commit()

    # --- email verification -------------------------------------------------

    async def request_email_verification(self, user_id: UUID) -> None:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        await self._issue_email_verification_token(user)

    async def resend_verification(self, email: str) -> None:
        """Generic response regardless of whether the email exists / is already verified."""
        user = await self.user_repo.get_by_email(email)
        if user is None or user.email_verified_at is not None:
            return None
        await self._issue_email_verification_token(user)

    async def _issue_email_verification_token(self, user: User) -> None:
        raw_token = generate_secure_token()
        expires_at = datetime.now(UTC) + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
        await self.email_verification_repo.create(
            user_id=user.id, token_hash=hash_token(raw_token), expires_at=expires_at
        )
        await self.session.commit()
        # TODO: send `raw_token` to the user via SMTP as a verification link.

    async def verify_email(self, raw_token: str) -> None:
        token_hash = hash_token(raw_token)
        token_record = await self.email_verification_repo.get_by_token_hash(token_hash)
        if token_record is None or not self.email_verification_repo.is_valid(token_record):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token"
            )

        user = await self.user_repo.get_by_id(token_record.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token"
            )

        user.is_email_verified = True
        user.email_verified_at = datetime.now(UTC)
        token_record.used_at = datetime.now(UTC)
        await self.session.flush()
        await self.audit_service.log_event(
            clinic_id=user.clinic_id, user_id=user.id, action="auth.email.verified",
            entity_type="user", entity_id=str(user.id),
        )
        await self.session.commit()
