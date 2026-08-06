"""Integration tests for Phase 4 Clinic Configuration & Master Data:
branches, departments, doctors, services, consultation rooms, queue
settings, operating hours, branding upload stub, and tenant isolation.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, clinic_slug: str, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": email, "password": password, "clinic_slug": clinic_slug},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    return clinic, {"Authorization": f"Bearer {token}"}


async def test_create_branch(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.post(
        "/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN", "status": "Active"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["code"] == "MAIN"


async def test_create_department(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.post(
        "/api/v1/departments",
        headers=headers,
        json={"department_code": "PED", "name": "Pediatrics", "color": "#f59e0b"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Pediatrics"

    # Duplicate code in same clinic conflicts.
    dup = await client.post(
        "/api/v1/departments", headers=headers, json={"department_code": "PED", "name": "Peds 2"}
    )
    assert dup.status_code == 409


async def test_create_doctor_generates_doctor_code(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.post(
        "/api/v1/doctors",
        headers=headers,
        json={"first_name": "Jose", "last_name": "Rizal", "specialization": "General Medicine"},
    )
    assert response.status_code == 201, response.text
    doctor = response.json()
    assert doctor["doctor_code"].startswith("DOC-")

    response2 = await client.post(
        "/api/v1/doctors", headers=headers, json={"first_name": "Maria", "last_name": "Clara"}
    )
    assert response2.json()["doctor_code"] != doctor["doctor_code"]


async def test_create_service(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.post(
        "/api/v1/services",
        headers=headers,
        json={"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": "500.00", "duration_minutes": 20},
    )
    assert response.status_code == 201, response.text
    assert response.json()["service_name"] == "Medical Certificate"


async def test_create_consultation_room(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.post(
        "/api/v1/consultation-rooms", headers=headers, json={"room_name": "Room 1", "room_number": "101"}
    )
    assert response.status_code == 201, response.text
    assert response.json()["room_name"] == "Room 1"


async def test_configure_queue_settings(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.put(
        "/api/v1/queue-settings",
        headers=headers,
        json={
            "queue_prefix": "A",
            "max_daily_queue": 150,
            "reset_time": "00:00:00",
            "allow_walkins": True,
            "allow_priority_lane": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["queue_prefix"] == "A"

    priority = await client.post(
        "/api/v1/queue-settings/priority-types", headers=headers, json={"code": "SENIOR", "label": "Senior Citizen"}
    )
    assert priority.status_code == 201, priority.text


async def test_upload_logo_stub_returns_expected_shape(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.post("/api/v1/clinic-settings/branding/logo/upload", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert "upload_url" in body and "public_url" in body and "expires_in" in body


async def test_configure_operating_hours(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)
    branch = await client.post("/api/v1/branches", headers=headers, json={"name": "Main"})
    branch_id = branch.json()["id"]

    response = await client.put(
        "/api/v1/operating-hours",
        headers=headers,
        json={
            "branch_id": branch_id,
            "day_of_week": 0,
            "opening_time": "08:00:00",
            "closing_time": "17:00:00",
            "is_closed": False,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["opening_time"] == "08:00:00"


async def test_doctor_tenant_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    clinic_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    created = await client.post(
        "/api/v1/doctors", headers=headers_a, json={"first_name": "Only", "last_name": "InA"}
    )
    doctor_id = created.json()["id"]

    # Clinic B cannot see clinic A's doctor.
    get_from_b = await client.get(f"/api/v1/doctors/{doctor_id}", headers=headers_b)
    assert get_from_b.status_code == 404

    list_from_b = await client.get("/api/v1/doctors", headers=headers_b)
    assert all(d["id"] != doctor_id for d in list_from_b.json()["items"])


async def test_service_tenant_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    clinic_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    created = await client.post(
        "/api/v1/services",
        headers=headers_a,
        json={"service_code": "ONLYA", "service_name": "Only In A", "default_price": "100.00"},
    )
    service_id = created.json()["id"]

    get_from_b = await client.get(f"/api/v1/services/{service_id}", headers=headers_b)
    assert get_from_b.status_code == 404

    # Clinic B can reuse the same service_code since uniqueness is per-clinic.
    create_same_code_b = await client.post(
        "/api/v1/services",
        headers=headers_b,
        json={"service_code": "ONLYA", "service_name": "Different Service", "default_price": "50.00"},
    )
    assert create_same_code_b.status_code == 201
