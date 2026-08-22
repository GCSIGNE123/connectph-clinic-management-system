"""Pydantic schemas for authentication endpoints."""

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import PasswordComplexityError, validate_password_complexity


class LoginRequest(BaseModel):
    email_or_username: str = Field(min_length=1, description="Email address or username.")
    password: str = Field(min_length=1)
    clinic_slug: str | None = Field(
        default=None, description="Optional clinic slug to disambiguate multi-clinic accounts."
    )
    remember_me: bool = False


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    clinic_name: str = Field(min_length=1, max_length=255)
    clinic_slug: str = Field(min_length=1, max_length=100)

    @field_validator("password")
    @classmethod
    def _validate_password_complexity(cls, value: str) -> str:
        try:
            validate_password_complexity(value)
        except PasswordComplexityError as exc:
            raise ValueError(str(exc)) from exc
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    clinic_id: UUID | None = None
    role: str | None = None


class RefreshRequest(BaseModel):
    """Body is optional: the refresh token is normally read from the httpOnly cookie."""

    refresh_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def _validate_password_complexity(cls, value: str) -> str:
        try:
            validate_password_complexity(value)
        except PasswordComplexityError as exc:
            raise ValueError(str(exc)) from exc
        return value


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class MeClinic(BaseModel):
    id: UUID
    name: str
    slug: str
    logo_url: str | None = None
    timezone: str
    created_at: str


class MeBranch(BaseModel):
    id: UUID
    clinic_id: UUID
    name: str


class MeResponse(BaseModel):
    id: UUID
    email: str
    first_name: str
    middle_name: str | None = None
    last_name: str
    mobile_number: str | None = None
    role: str
    clinic_id: UUID
    clinic: MeClinic | None = None
    branch_id: UUID | None = None
    branch: MeBranch | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: str
    updated_at: str
    # Round 6 (Laboratory Report Signatories): a Laboratory-role user's own
    # professional license/registration number, plus whether they currently
    # have an e-signature configured (never the raw stored filename - the
    # signature image itself is fetched via the authenticated
    # `/auth/me/signature/file` endpoint, same pattern as Doctor e-signatures).
    license_number: str | None = None
    has_signature: bool = False


class UpdateOwnProfileRequest(BaseModel):
    """Self-service profile update - deliberately excludes role_id/branch_id/
    email/username (privilege- or identity-affecting fields), unlike the
    Owner/Administrator-only `UserUpdate` schema used by `/users/{id}`."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    mobile_number: str | None = Field(default=None, max_length=20)
    # Round 6: a Laboratory-role user's own professional license/
    # registration number, printed under their signature on the Laboratory
    # Report when they release results as Med Tech In Charge.
    license_number: str | None = Field(default=None, max_length=50)

    @field_validator("mobile_number")
    @classmethod
    def _check_mobile_number(cls, value: str | None) -> str | None:
        from app.schemas.user import MOBILE_NUMBER_PATTERN  # noqa: PLC0415

        if value is not None and not MOBILE_NUMBER_PATTERN.match(value):
            raise ValueError("Mobile number must be 7-15 digits, optionally prefixed with '+'.")
        return value


class ChangeOwnPasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def _validate_password_complexity(cls, value: str) -> str:
        try:
            validate_password_complexity(value)
        except PasswordComplexityError as exc:
            raise ValueError(str(exc)) from exc
        return value
