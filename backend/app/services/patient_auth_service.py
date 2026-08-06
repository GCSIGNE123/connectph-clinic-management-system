"""Login/logout/refresh/forgot-reset for the Patient Portal.

Separate from `app.services.auth_service.AuthService` (clinic-user auth) and
`app.services.platform_admin_auth_service.PlatformAdminAuthService`
(Phase 15). Issues tokens via `app.core.patient_security`, never
`app.core.security.create_access_token` or
`app.core.platform_admin_security.create_platform_access_token`.

Forgot-password/reset-password reuses the SAME pattern as the existing
clinic-staff flow (`AuthService.forgot_password`/`reset_password`:
`generate_secure_token()` + `hash_token()` + a single-use expiring row) but
against the patient-scoped `patient_password_reset_tokens` table - never
`password_reset_tokens` (staff-only), so a patient reset token can never be
replayed against the staff reset endpoint and vice versa.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.patient_security import (
    PatientTokenType,
    create_patient_access_token,
    create_patient_refresh_token,
    decode_patient_token,
)
from app.core.security import (
    TokenPayloadError,
    generate_secure_token,
    hash_password,
    hash_token,
    validate_password_complexity,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.patient import Patient
from app.models.patient_account import PatientAccount, PatientPasswordResetToken
from app.repositories.patient_account_repository import PatientAccountRepository

RESET_TOKEN_EXPIRE_MINUTES = 30


class PatientAuthResult:
    def __init__(self, *, access_token: str, refresh_token: str, account: PatientAccount, patient: Patient) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.account = account
        self.patient = patient


class PatientAuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = PatientAccountRepository(session)

    async def _audit(
        self, *, clinic_id: UUID, patient_id: UUID | None, action: str, ip_address: str | None, user_agent: str | None
    ) -> None:
        self.session.add(
            AuditLog(
                clinic_id=clinic_id,
                user_id=None,
                action=action,
                entity_type="patient",
                entity_id=str(patient_id) if patient_id else None,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata_json={"principal": "patient"},
            )
        )

    async def login(
        self, *, identifier: str, password: str, ip_address: str | None, user_agent: str | None
    ) -> PatientAuthResult:
        found = await self.repo.get_by_identifier(identifier)
        if found is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        account, patient = found
        if not account.is_active or not verify_password(password, account.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        access_token = create_patient_access_token(
            patient_account_id=account.id, patient_id=patient.id, clinic_id=patient.clinic_id
        )
        refresh_token = create_patient_refresh_token(
            patient_account_id=account.id, patient_id=patient.id, clinic_id=patient.clinic_id
        )
        account.last_login_at = datetime.now(UTC)
        await self.session.flush()

        # Security requirement (Phase 18): audit-log EVERY patient login.
        await self._audit(
            clinic_id=patient.clinic_id, patient_id=patient.id, action="patient.login",
            ip_address=ip_address, user_agent=user_agent,
        )
        await self.session.commit()
        return PatientAuthResult(access_token=access_token, refresh_token=refresh_token, account=account, patient=patient)

    async def refresh(self, raw_refresh_token: str) -> PatientAuthResult:
        try:
            payload = decode_patient_token(raw_refresh_token, expected_type=PatientTokenType.REFRESH)
        except TokenPayloadError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

        found = await self.repo.get_with_patient(UUID(payload["patient_account_id"]))
        if found is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Patient account not found")
        account, patient = found
        if not account.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Patient account is inactive")

        access_token = create_patient_access_token(
            patient_account_id=account.id, patient_id=patient.id, clinic_id=patient.clinic_id
        )
        new_refresh = create_patient_refresh_token(
            patient_account_id=account.id, patient_id=patient.id, clinic_id=patient.clinic_id
        )
        return PatientAuthResult(access_token=access_token, refresh_token=new_refresh, account=account, patient=patient)

    async def forgot_password(self, identifier: str) -> None:
        found = await self.repo.get_by_identifier(identifier)
        if found is None:
            return  # Do not reveal whether an account exists.
        account, _patient = found

        raw_token = generate_secure_token()
        self.session.add(
            PatientPasswordResetToken(
                patient_account_id=account.id,
                token_hash=hash_token(raw_token),
                expires_at=datetime.now(UTC) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
            )
        )
        await self.session.commit()
        # NOTE: actual email delivery reuses the same "log/print in dev, no
        # SMTP configured" stub as `AuthService.forgot_password` - see that
        # method for the TODO on real email provider integration.

    async def reset_password(self, raw_token: str, new_password: str) -> None:
        from sqlalchemy import select  # noqa: PLC0415

        validate_password_complexity(new_password)
        token_hash = hash_token(raw_token)
        result = await self.session.execute(
            select(PatientPasswordResetToken).where(PatientPasswordResetToken.token_hash == token_hash)
        )
        token_row = result.scalar_one_or_none()
        if (
            token_row is None
            or token_row.used_at is not None
            or token_row.expires_at < datetime.now(UTC)
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        account = await self.repo.get_by_id(token_row.patient_account_id)
        if account is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")

        account.password_hash = hash_password(new_password)
        token_row.used_at = datetime.now(UTC)
        await self.session.commit()

    async def change_password(self, *, account: PatientAccount, old_password: str, new_password: str) -> None:
        if not verify_password(old_password, account.password_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        validate_password_complexity(new_password)
        account.password_hash = hash_password(new_password)
        await self.session.flush()
        await self.session.commit()
