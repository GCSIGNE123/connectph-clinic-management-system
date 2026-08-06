"""Pydantic schemas for user resources."""

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import PasswordComplexityError, validate_password_complexity
from app.models.user import UserStatus

MOBILE_NUMBER_PATTERN = re.compile(r"^\+?[0-9]{7,15}$")


def _validate_mobile_number(value: str | None) -> str | None:
    if value is None:
        return value
    if not MOBILE_NUMBER_PATTERN.match(value):
        raise ValueError("Mobile number must be 7-15 digits, optionally prefixed with '+'.")
    return value


class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    mobile_number: str | None = Field(default=None, max_length=20)

    @field_validator("mobile_number")
    @classmethod
    def _check_mobile_number(cls, value: str | None) -> str | None:
        return _validate_mobile_number(value)


class UserCreate(UserBase):
    password: str = Field(min_length=8)
    role_id: UUID
    branch_id: UUID | None = None

    @field_validator("password")
    @classmethod
    def _validate_password_complexity(cls, value: str) -> str:
        try:
            validate_password_complexity(value)
        except PasswordComplexityError as exc:
            raise ValueError(str(exc)) from exc
        return value


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    mobile_number: str | None = Field(default=None, max_length=20)
    profile_photo: str | None = Field(default=None, max_length=500)
    role_id: UUID | None = None
    branch_id: UUID | None = None

    @field_validator("mobile_number")
    @classmethod
    def _check_mobile_number(cls, value: str | None) -> str | None:
        return _validate_mobile_number(value)


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def _validate_password_complexity(cls, value: str) -> str:
        try:
            validate_password_complexity(value)
        except PasswordComplexityError as exc:
            raise ValueError(str(exc)) from exc
        return value


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    role_id: UUID
    role_name: str | None = None
    branch_id: UUID | None = None
    doctor_id: UUID | None = None
    profile_photo: str | None = None
    is_active: bool
    is_email_verified: bool
    status: UserStatus
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int
