"""JWT issuance/verification for Patient Portal accounts.

Deliberately separate from `app.core.security` (clinic-user tokens) and
`app.core.platform_admin_security` (platform-admin tokens) - mirrors the
Phase 15 precedent exactly. A patient access token has a structurally
different claim shape from either:

    Clinic-user access token:   {"sub": user_id, "user_id": ..., "clinic_id": ...,
                                  "role": <RoleName>, "type": "access", ...}
    Platform-admin access token: {"sub": platform_admin_id, "platform_admin_id": ...,
                                   "platform_admin_role": ..., "type": "platform_admin_access", ...}
    Patient access token:        {"sub": patient_account_id, "patient_id": ...,
                                   "patient_account_id": ..., "clinic_id": ...,
                                   "type": "patient_access", ...}

The `type` claim values never overlap across all three, and only the patient
payload has both `patient_id` and `patient_account_id` claims. This means:
  - `get_current_user` 401s on a patient token (wrong `type`, no `user_id`).
  - `get_current_platform_admin` 401s on a patient token (wrong `type`, no
    `platform_admin_id`).
  - `get_current_patient` (app/core/dependencies.py) 401s on a clinic-staff
    or platform-admin token for the same reason, in reverse.
"""

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import UUID

from jose import JWTError, jwt

from app.core.config import settings
from app.core.security import TokenPayloadError


class PatientTokenType(str, Enum):
    ACCESS = "patient_access"
    REFRESH = "patient_refresh"


PATIENT_ACCESS_TOKEN_EXPIRE_MINUTES = 30
PATIENT_REFRESH_TOKEN_EXPIRE_DAYS = 14


def _create_patient_token(
    *,
    patient_account_id: UUID | str,
    patient_id: UUID | str,
    clinic_id: UUID | str,
    token_type: PatientTokenType,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(patient_account_id),
        "patient_account_id": str(patient_account_id),
        "patient_id": str(patient_id),
        "clinic_id": str(clinic_id),
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_patient_access_token(*, patient_account_id: UUID | str, patient_id: UUID | str, clinic_id: UUID | str) -> str:
    return _create_patient_token(
        patient_account_id=patient_account_id,
        patient_id=patient_id,
        clinic_id=clinic_id,
        token_type=PatientTokenType.ACCESS,
        expires_delta=timedelta(minutes=PATIENT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_patient_refresh_token(*, patient_account_id: UUID | str, patient_id: UUID | str, clinic_id: UUID | str) -> str:
    return _create_patient_token(
        patient_account_id=patient_account_id,
        patient_id=patient_id,
        clinic_id=clinic_id,
        token_type=PatientTokenType.REFRESH,
        expires_delta=timedelta(days=PATIENT_REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_patient_token(token: str, *, expected_type: PatientTokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise TokenPayloadError(f"Invalid or expired token: {exc}") from exc

    if expected_type is not None and payload.get("type") != expected_type.value:
        raise TokenPayloadError(f"Expected token type '{expected_type.value}', got '{payload.get('type')}'")
    # Guard against a clinic-user/platform-admin token ever being accepted
    # here even if the `type` string were somehow forged to match: require
    # the patient-only claims.
    if "patient_account_id" not in payload or "patient_id" not in payload:
        raise TokenPayloadError("Not a patient-portal token")
    return payload
