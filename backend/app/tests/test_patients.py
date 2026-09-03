"""Integration tests for patient CRUD: create/edit/duplicate-detection/
archive/restore/search/pagination/tenant-isolation.
"""

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """This file logs in via the real endpoint multiple times per test
    (Owner + a role-specific user for several of them) - reusing the same
    per-test reset already used by `test_queues.py`/`test_tv_display.py`/
    `test_billing.py` (see BUG-034) so this file's own login count never
    trips the shared, real, non-test-mode-bypassed rate limiter within a
    single pytest run. Test-isolation-only; no production code path is
    affected."""
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


async def _login(client: AsyncClient, clinic_slug: str, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": email, "password": password, "clinic_slug": clinic_slug},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _patient_payload(**overrides) -> dict:
    payload = {
        "first_name": "Juan",
        "middle_name": "Santos",
        "last_name": "Dela Cruz",
        "birth_date": "1990-05-15",
        "gender": "Male",
        "civil_status": "Single",
        "nationality": "Filipino",
        "address_line": "123 Rizal St",
        "barangay": "Poblacion",
        "city": "Quezon City",
        "province": "Metro Manila",
        "zip_code": "1100",
        "mobile_number": "+639171234567",
        "email": "juan.delacruz@example.com",
    }
    payload.update(overrides)
    return payload


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    return clinic, {"Authorization": f"Bearer {token}"}


async def test_create_patient_generates_patient_number(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    response = await client.post("/api/v1/patients", headers=headers, json=_patient_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["duplicates"] == []
    patient = body["patient"]
    assert patient["patient_number"].startswith("PAT-")
    assert patient["status"] == "Active"
    assert patient["qr_code"]

    # A second patient in the same clinic gets the next sequential number.
    response2 = await client.post(
        "/api/v1/patients", headers=headers, json=_patient_payload(mobile_number="+639171234568", first_name="Maria")
    )
    assert response2.status_code == 201, response2.text
    patient2 = response2.json()["patient"]
    assert patient2["patient_number"] != patient["patient_number"]


async def test_edit_patient_field_diff_and_audit(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    create_response = await client.post("/api/v1/patients", headers=headers, json=_patient_payload())
    patient_id = create_response.json()["patient"]["id"]

    update_response = await client.put(
        f"/api/v1/patients/{patient_id}",
        headers=headers,
        json={"occupation": "Engineer", "city": "Makati City"},
    )
    assert update_response.status_code == 200, update_response.text
    updated = update_response.json()["patient"]
    assert updated["occupation"] == "Engineer"
    assert updated["city"] == "Makati City"

    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "patient.updated", AuditLog.entity_id == patient_id)
    )
    audit_entry = result.scalars().first()
    assert audit_entry is not None
    assert "occupation" in audit_entry.metadata_json["fields"]
    assert "city" in audit_entry.metadata_json["fields"]


async def test_duplicate_detection_same_name_and_dob(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    first = await client.post("/api/v1/patients", headers=headers, json=_patient_payload())
    assert first.status_code == 201

    duplicate_attempt = await client.post(
        "/api/v1/patients", headers=headers, json=_patient_payload(mobile_number="+639170000000")
    )
    assert duplicate_attempt.status_code == 201
    body = duplicate_attempt.json()
    assert body["patient"] is None
    assert len(body["duplicates"]) == 1
    assert body["duplicates"][0]["match_reason"] == "Same name and date of birth"

    override_attempt = await client.post(
        "/api/v1/patients?override=true", headers=headers, json=_patient_payload(mobile_number="+639170000000")
    )
    assert override_attempt.status_code == 201
    assert override_attempt.json()["patient"] is not None


async def test_duplicate_detection_same_mobile_number(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    await client.post("/api/v1/patients", headers=headers, json=_patient_payload())

    duplicate_attempt = await client.post(
        "/api/v1/patients",
        headers=headers,
        json=_patient_payload(first_name="Different", last_name="Person", birth_date="1985-01-01"),
    )
    assert duplicate_attempt.status_code == 201
    body = duplicate_attempt.json()
    assert body["patient"] is None
    assert body["duplicates"][0]["match_reason"] == "Same mobile number"


async def test_archive_and_restore_patient(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    create_response = await client.post("/api/v1/patients", headers=headers, json=_patient_payload())
    patient_id = create_response.json()["patient"]["id"]

    archive_response = await client.post(f"/api/v1/patients/{patient_id}/archive", headers=headers)
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "Archived"

    restore_response = await client.post(f"/api/v1/patients/{patient_id}/restore", headers=headers)
    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "Active"


async def test_search_by_various_fields(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    await client.post(
        "/api/v1/patients",
        headers=headers,
        json=_patient_payload(
            first_name="Searchable", last_name="Person", mobile_number="+639175551234",
            email="searchable@example.com",
        ),
    )

    for query in ["Searchable", "Person", "+639175551234", "searchable@example.com"]:
        response = await client.get("/api/v1/patients", headers=headers, params={"q": query})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] >= 1, f"no match for query={query}"


async def test_pagination(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, headers = await _owner_headers(client, make_clinic_with_owner)

    for i in range(3):
        response = await client.post(
            "/api/v1/patients",
            headers=headers,
            json=_patient_payload(
                first_name=f"Page{i}", mobile_number=f"+63917000{i:04d}", birth_date="1995-01-01"
            ),
        )
        assert response.status_code == 201

    response = await client.get("/api/v1/patients", headers=headers, params={"limit": 2, "offset": 0})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0


async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    clinic_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    clinic_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    create_response = await client.post("/api/v1/patients", headers=headers_a, json=_patient_payload())
    patient_id = create_response.json()["patient"]["id"]

    # Clinic B cannot view clinic A's patient.
    get_response = await client.get(f"/api/v1/patients/{patient_id}", headers=headers_b)
    assert get_response.status_code == 404

    # Clinic B cannot edit clinic A's patient either.
    update_response = await client.put(
        f"/api/v1/patients/{patient_id}", headers=headers_b, json={"occupation": "Hacked"}
    )
    assert update_response.status_code == 404

    # Clinic B's patient list never includes clinic A's patient.
    list_response = await client.get("/api/v1/patients", headers=headers_b)
    ids = {item["id"] for item in list_response.json()["items"]}
    assert patient_id not in ids


async def test_viewer_role_is_read_only(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.role import Role
    from app.models.user import User

    clinic, _headers = await _owner_headers(client, make_clinic_with_owner)

    result = await db_session.execute(select(Role).where(Role.name == "Viewer"))
    viewer_role = result.scalar_one()

    viewer = User(
        clinic_id=clinic.id,
        email="viewer@example.com",
        username="viewer1",
        hashed_password=hash_password("ViewerPass1!"),
        first_name="View",
        last_name="Only",
        role_id=viewer_role.id,
        is_active=True,
    )
    db_session.add(viewer)
    await db_session.commit()

    token = await _login(client, clinic.slug, "viewer@example.com", "ViewerPass1!")
    headers = {"Authorization": f"Bearer {token}"}

    list_response = await client.get("/api/v1/patients", headers=headers)
    assert list_response.status_code == 200

    create_response = await client.post("/api/v1/patients", headers=headers, json=_patient_payload())
    assert create_response.status_code == 403


async def _make_role_headers(client: AsyncClient, db_session, *, clinic, role_name: str) -> dict:
    """Creates a real user of `role_name` in `clinic` (direct DB write, no
    HTTP round-trip needed for setup - same pattern as
    `test_viewer_role_is_read_only` above and `test_queues.py::_make_role_login`)
    and returns Authorization headers for a freshly logged-in session."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.role import Role
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"{role_name.lower()}-{suffix}@example.com"
    user = User(
        clinic_id=clinic.id, email=email, username=f"{role_name.lower()}{suffix}",
        hashed_password=hash_password("TestPass123!"), first_name="Test", last_name=role_name,
        role_id=role.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = await _login(client, clinic.slug, email, "TestPass123!")
    return {"Authorization": f"Bearer {token}"}


async def test_receptionist_can_list_and_create_patients(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Receptionist RBAC requirement: see/search all of their clinic's
    patients and create a patient - the exact two actions reported broken
    ("Not authenticated" on create, "No patients found" on list) in the
    receptionist patient-access production incident. `PATIENT_VIEW_ROLES`/
    `PATIENT_MANAGE_ROLES` already include Receptionist (see
    `core/dependencies.py`) - this proves the whole request path (auth ->
    role gate -> clinic scoping -> repository query) actually honors that,
    not just the role-set constant in isolation."""
    clinic, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    # A pre-existing patient (created by the Owner) that the Receptionist
    # must be able to see - proves this isn't just "can create", but also
    # "can see records that already exist" (the reported "No patients
    # found" symptom).
    existing = await client.post("/api/v1/patients", headers=owner_headers, json=_patient_payload())
    assert existing.status_code == 201, existing.text
    existing_id = existing.json()["patient"]["id"]

    receptionist_headers = await _make_role_headers(
        client, db_session, clinic=clinic, role_name="Receptionist"
    )

    list_response = await client.get("/api/v1/patients", headers=receptionist_headers)
    assert list_response.status_code == 200, list_response.text
    ids = {item["id"] for item in list_response.json()["items"]}
    assert existing_id in ids

    create_response = await client.post(
        "/api/v1/patients",
        headers=receptionist_headers,
        json=_patient_payload(
            first_name="Maria",
            last_name="Santos",
            mobile_number="+639171112222",
            email="maria.santos@example.com",
        ),
    )
    assert create_response.status_code == 201, create_response.text
    assert create_response.json()["patient"] is not None


async def test_unauthenticated_patient_requests_rejected(client: AsyncClient) -> None:
    """No Authorization header at all - the exact `get_current_user`/
    `get_current_clinic_id` branch that produces the reported "Not
    authenticated" error - must 401 on both list and create, with no clinic
    context ever resolved."""
    list_response = await client.get("/api/v1/patients")
    assert list_response.status_code == 401
    assert list_response.json()["detail"] == "Not authenticated"

    create_response = await client.post("/api/v1/patients", json=_patient_payload())
    assert create_response.status_code == 401
    assert create_response.json()["detail"] == "Not authenticated"
