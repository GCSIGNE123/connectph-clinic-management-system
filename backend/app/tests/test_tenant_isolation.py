"""Tests asserting one clinic (tenant) cannot see or edit another clinic's users."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, clinic_slug: str, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": email, "password": password, "clinic_slug": clinic_slug},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_clinic_a_cannot_read_clinic_b_user(client: AsyncClient, make_clinic_with_owner, owner_role) -> None:
    clinic_a, owner_a, password_a = await make_clinic_with_owner()
    clinic_b, owner_b, password_b = await make_clinic_with_owner()

    token_a = await _login(client, clinic_a.slug, owner_a.email, password_a)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Clinic A tries to fetch clinic B's owner by id -> must 404, not leak data.
    response = await client.get(f"/api/v1/users/{owner_b.id}", headers=headers_a)
    assert response.status_code == 404


async def test_clinic_a_user_list_excludes_clinic_b_users(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    clinic_a, owner_a, password_a = await make_clinic_with_owner()
    clinic_b, owner_b, _password_b = await make_clinic_with_owner()

    token_a = await _login(client, clinic_a.slug, owner_a.email, password_a)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    list_response = await client.get("/api/v1/users", headers=headers_a)
    assert list_response.status_code == 200
    emails = {item["email"] for item in list_response.json()["items"]}
    assert owner_b.email not in emails
    assert owner_a.email in emails


async def test_clinic_a_cannot_disable_clinic_b_user(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic_a, owner_a, password_a = await make_clinic_with_owner()
    clinic_b, owner_b, _password_b = await make_clinic_with_owner()

    token_a = await _login(client, clinic_a.slug, owner_a.email, password_a)
    headers_a = {"Authorization": f"Bearer {token_a}"}

    response = await client.post(f"/api/v1/users/{owner_b.id}/disable", headers=headers_a)
    assert response.status_code == 404
