"""JWT issuance/verification for Platform Administration Portal accounts.

Deliberately separate from `app.core.security`'s clinic-user token functions.
A platform-admin access token has a *structurally different claim shape* from
a clinic-user access token:

    Clinic-user access token:   {"sub": user_id, "user_id": ..., "clinic_id": ...,
                                  "role": <RoleName>, "type": "access", ...}
    Platform-admin access token: {"sub": platform_admin_user_id,
                                   "platform_admin_id": ...,
                                   "platform_admin_role": <PlatformAdminRole>,
                                   "type": "platform_admin_access", ...}

The `type` claim values never overlap ("access"/"refresh" vs.
"platform_admin_access"/"platform_admin_refresh"), and the platform-admin
payload has no `clinic_id` key at all. This means:

  - `app.core.dependencies.get_current_user` (which requires `type == "access"`
    and reads `user_id`) will 401 on a platform-admin token: the type check
    fails first.
  - `app.core.dependencies.get_current_platform_admin` (below) will 401 on a
    clinic-user token for the same reason, in reverse.

There is no shared secret-reuse risk beyond both using `settings.JWT_SECRET_KEY`
for signing (same as every other JWT in this app) - the separation that
matters is the claim shape / `type` value, not the signing key.
"""

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import TokenPayloadError


class PlatformTokenType(str, Enum):
    ACCESS = "platform_admin_access"
    REFRESH = "platform_admin_refresh"


PLATFORM_ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES = 30
PLATFORM_ADMIN_REFRESH_TOKEN_EXPIRE_DAYS = 7


def _create_platform_token(
    *,
    platform_admin_id: UUID | str,
    role: str,
    token_type: PlatformTokenType,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(platform_admin_id),
        "platform_admin_id": str(platform_admin_id),
        "platform_admin_role": role,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_platform_access_token(*, platform_admin_id: UUID | str, role: str) -> str:
    return _create_platform_token(
        platform_admin_id=platform_admin_id,
        role=role,
        token_type=PlatformTokenType.ACCESS,
        expires_delta=timedelta(minutes=PLATFORM_ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_platform_refresh_token(*, platform_admin_id: UUID | str, role: str) -> str:
    return _create_platform_token(
        platform_admin_id=platform_admin_id,
        role=role,
        token_type=PlatformTokenType.REFRESH,
        expires_delta=timedelta(days=PLATFORM_ADMIN_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_platform_token(token: str, *, expected_type: PlatformTokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise TokenPayloadError(f"Invalid or expired token: {exc}") from exc

    if expected_type is not None and payload.get("type") != expected_type.value:
        raise TokenPayloadError(f"Expected token type '{expected_type.value}', got '{payload.get('type')}'")
    # Guard against a clinic-user token ever being accepted here even if the
    # `type` string were somehow forged to match: require the platform-only claim.
    if "platform_admin_id" not in payload:
        raise TokenPayloadError("Not a platform-admin token")
    return payload
