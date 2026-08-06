"""Integration tests for user CRUD: create/edit/disable/enable/search/pagination."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, clinic_slug: str, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": email, "password": password, "clinic_slug": clinic_slug},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_owner_can_create_and_list_users(client: AsyncClient, make_clinic_with_owner, owner_role) -> None:
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "newstaff@example.com",
            "username": "newstaff1",
            "password": "AnotherPass1!",
            "first_name": "New",
            "last_name": "Staff",
            "role_id": str(owner_role.id),
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["email"] == "newstaff@example.com"
    assert created["status"] == "active"

    list_response = await client.get("/api/v1/users", headers=headers)
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] >= 2  # owner + newly created staff
    emails = {item["email"] for item in body["items"]}
    assert "newstaff@example.com" in emails


async def test_update_disable_enable_user(client: AsyncClient, make_clinic_with_owner, owner_role) -> None:
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "staff2@example.com",
            "username": "staff2",
            "password": "AnotherPass1!",
            "first_name": "Staff",
            "last_name": "Two",
            "role_id": str(owner_role.id),
        },
    )
    user_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/api/v1/users/{user_id}", headers=headers, json={"first_name": "Updated"}
    )
    assert update_response.status_code == 200
    assert update_response.json()["first_name"] == "Updated"

    disable_response = await client.post(f"/api/v1/users/{user_id}/disable", headers=headers)
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "disabled"
    assert disable_response.json()["is_active"] is False

    # A disabled user cannot log in.
    disabled_login = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": "staff2@example.com", "password": "AnotherPass1!", "clinic_slug": clinic.slug},
    )
    assert disabled_login.status_code == 403

    enable_response = await client.post(f"/api/v1/users/{user_id}/enable", headers=headers)
    assert enable_response.status_code == 200
    assert enable_response.json()["status"] == "active"

    enabled_login = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": "staff2@example.com", "password": "AnotherPass1!", "clinic_slug": clinic.slug},
    )
    assert enabled_login.status_code == 200


async def test_admin_reset_password(client: AsyncClient, make_clinic_with_owner, owner_role) -> None:
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    create_response = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "staff3@example.com",
            "username": "staff3",
            "password": "OldPassword1!",
            "first_name": "Staff",
            "last_name": "Three",
            "role_id": str(owner_role.id),
        },
    )
    user_id = create_response.json()["id"]

    reset_response = await client.post(
        f"/api/v1/users/{user_id}/reset-password", headers=headers, json={"new_password": "BrandNewPass9!"}
    )
    assert reset_response.status_code == 200

    login_with_new_password = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": "staff3@example.com", "password": "BrandNewPass9!", "clinic_slug": clinic.slug},
    )
    assert login_with_new_password.status_code == 200


async def test_search_and_pagination(client: AsyncClient, make_clinic_with_owner, owner_role) -> None:
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(3):
        response = await client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": f"findme{i}@example.com",
                "username": f"findme{i}",
                "password": "AnotherPass1!",
                "first_name": "Findable",
                "last_name": f"Person{i}",
                "role_id": str(owner_role.id),
            },
        )
        assert response.status_code == 201

    search_response = await client.get("/api/v1/users", headers=headers, params={"q": "findable", "limit": 2})
    assert search_response.status_code == 200
    body = search_response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0


async def test_non_owner_role_cannot_manage_users(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    from app.core.security import hash_password
    from app.models.role import Role
    from app.models.user import User

    clinic, owner, _password = await make_clinic_with_owner()

    result = await db_session.execute(select(Role).where(Role.name == "Receptionist"))
    receptionist_role = result.scalar_one()

    receptionist = User(
        clinic_id=clinic.id,
        email="reception@example.com",
        username="reception1",
        hashed_password=hash_password("ReceptionPass1!"),
        first_name="Front",
        last_name="Desk",
        role_id=receptionist_role.id,
        is_active=True,
    )
    db_session.add(receptionist)
    await db_session.commit()

    token = await _login(client, clinic.slug, "reception@example.com", "ReceptionPass1!")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/v1/users", headers=headers)
    assert response.status_code == 403
