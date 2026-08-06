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
    last_name: str
    role: str
    clinic_id: UUID
    clinic: MeClinic | None = None
    branch_id: UUID | None = None
    branch: MeBranch | None = None
    avatar_url: str | None = None
    is_active: bool
    created_at: str
    updated_at: str
