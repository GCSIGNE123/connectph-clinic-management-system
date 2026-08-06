"""Password hashing and JWT token creation/validation utilities."""

import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

PASSWORD_MIN_LENGTH = 8


class PasswordComplexityError(ValueError):
    """Raised when a candidate password fails complexity requirements."""


def validate_password_complexity(password: str) -> None:
    """Enforce a baseline password complexity policy.

    Requires: minimum length, at least one uppercase, one lowercase, one digit,
    and one special character. Raises `PasswordComplexityError` with a
    human-readable message on failure.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordComplexityError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")
    if not re.search(r"[A-Z]", password):
        raise PasswordComplexityError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise PasswordComplexityError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise PasswordComplexityError("Password must contain at least one digit.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise PasswordComplexityError("Password must contain at least one special character.")


def generate_secure_token(*, num_bytes: int = 32) -> str:
    """Generate a cryptographically secure, URL-safe random token (opaque, not a JWT)."""
    return secrets.token_urlsafe(num_bytes)


def hash_token(token: str) -> str:
    """Hash an opaque token for storage (SHA-256 hex digest, deterministic for lookup)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayloadError(Exception):
    """Raised when a JWT cannot be decoded or fails validation."""


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(
    *,
    user_id: UUID | str,
    clinic_id: UUID | str | None,
    role: str | None,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "user_id": str(user_id),
        "clinic_id": str(clinic_id) if clinic_id is not None else None,
        "role": role,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    *,
    user_id: UUID | str,
    clinic_id: UUID | str | None,
    role: str | None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    return _create_token(
        user_id=user_id,
        clinic_id=clinic_id,
        role=role,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims=extra_claims,
    )


def create_refresh_token(
    *,
    user_id: UUID | str,
    clinic_id: UUID | str | None,
    role: str | None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    return _create_token(
        user_id=user_id,
        clinic_id=clinic_id,
        role=role,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        extra_claims=extra_claims,
    )


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError as exc:
        raise TokenPayloadError(f"Invalid or expired token: {exc}") from exc

    if expected_type is not None and payload.get("type") != expected_type.value:
        raise TokenPayloadError(
            f"Expected token type '{expected_type.value}', got '{payload.get('type')}'"
        )
    return payload
