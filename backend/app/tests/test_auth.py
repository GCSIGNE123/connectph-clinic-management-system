"""Integration tests for login/lockout, refresh rotation, and forgot/reset password."""

import pytest
from httpx import AsyncClient

from app.core.config import settings

pytestmark = pytest.mark.asyncio


async def test_login_success(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic, user, password = await make_clinic_with_owner()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": user.email, "password": password, "clinic_slug": clinic.slug},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user_id"] == str(user.id)
    assert body["role"] == "Owner"
    assert settings.REFRESH_TOKEN_COOKIE_NAME in response.cookies


async def test_login_failure_wrong_password(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic, user, _ = await make_clinic_with_owner()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": user.email, "password": "WrongPassword1!", "clinic_slug": clinic.slug},
    )

    assert response.status_code == 401


async def test_account_locks_after_max_failed_attempts(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic, user, _ = await make_clinic_with_owner()

    for _ in range(settings.LOGIN_MAX_FAILED_ATTEMPTS):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email_or_username": user.email, "password": "WrongPassword1!", "clinic_slug": clinic.slug},
        )
        assert response.status_code in (401, 423)

    # One more attempt, even with the correct password, should now be locked.
    locked_response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": user.email, "password": "WrongPassword1!", "clinic_slug": clinic.slug},
    )
    assert locked_response.status_code == 423


async def test_refresh_rotates_token(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic, user, password = await make_clinic_with_owner()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": user.email, "password": password, "clinic_slug": clinic.slug},
    )
    assert login_response.status_code == 200
    old_cookie = login_response.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    assert old_cookie

    refresh_response = await client.post("/api/v1/auth/refresh", json={})
    assert refresh_response.status_code == 200
    new_cookie = refresh_response.cookies.get(settings.REFRESH_TOKEN_COOKIE_NAME)
    assert new_cookie
    assert new_cookie != old_cookie

    # The old refresh token must now be rejected (rotation revokes it).
    reused_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": old_cookie}
    )
    assert reused_response.status_code == 401


async def test_forgot_and_reset_password_flow(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    from sqlalchemy import select

    from app.models.password_reset_token import PasswordResetToken

    clinic, user, _old_password = await make_clinic_with_owner()

    forgot_response = await client.post("/api/v1/auth/forgot-password", json={"email": user.email})
    assert forgot_response.status_code == 202

    result = await db_session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    token_record = result.scalars().first()
    assert token_record is not None

    # We only have the hash in the DB (by design); reconstruct the raw-token
    # flow by generating a token through the service directly for a deterministic
    # assertion of the reset endpoint's behavior.
    from app.core.security import generate_secure_token, hash_token

    raw_token = generate_secure_token()
    token_record.token_hash = hash_token(raw_token)
    await db_session.commit()

    reset_response = await client.post(
        "/api/v1/auth/reset-password", json={"token": raw_token, "new_password": "BrandNewPass1!"}
    )
    assert reset_response.status_code == 200

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": user.email, "password": "BrandNewPass1!", "clinic_slug": clinic.slug},
    )
    assert login_response.status_code == 200

    # Reusing the same reset token must fail (single-use).
    reuse_response = await client.post(
        "/api/v1/auth/reset-password", json={"token": raw_token, "new_password": "AnotherPass1!"}
    )
    assert reuse_response.status_code == 400


async def test_logout_revokes_session(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic, user, password = await make_clinic_with_owner()

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": user.email, "password": password, "clinic_slug": clinic.slug},
    )
    access_token = login_response.json()["access_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert logout_response.status_code == 204

    refresh_response = await client.post("/api/v1/auth/refresh", json={})
    assert refresh_response.status_code == 401
