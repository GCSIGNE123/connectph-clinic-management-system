"""Integration tests for Phase 14 Legacy Migration Wizard.

Focus is the critical path spec calls out explicitly: create a batch from
a small CSV sample, analyze/detect fields, mapping suggestion produces
sensible defaults, validation flags a deliberately-broken row without
flagging valid ones, preview computes correct counts, import creates real
Patient/Doctor rows with legacy provenance populated, **running the same
import twice does not create duplicate rows** (idempotency - the single
most important test here), role gating, and tenant isolation.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.doctor import Doctor
from app.models.patient import Patient
from app.models.role import Role

pytestmark = pytest.mark.asyncio

PATIENTS_CSV = (
    b"id,FName,LName,DOB,Gender,CivilStatus,Mobile,Email\n"
    b"1,TEST-IMPORT,PatientOne,1990-01-15,Male,Single,+639171234561,test1@example.com\n"
    b"2,TEST-IMPORT,PatientTwo,1985-06-20,Female,Married,+639171234562,test2@example.com\n"
    b"3,TEST-IMPORT,PatientBroken,,Male,Single,,bad-email\n"
)
DOCTORS_CSV = (
    b"id,FName,LName,Specialization,Email\n"
    b"1,TEST-IMPORT,DoctorOne,General Medicine,doc1@example.com\n"
)


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email_or_username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, owner.email, password)
    return clinic, owner, {"Authorization": f"Bearer {token}"}


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, password: str = "TestPass123!"):
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"{role_name.lower()}-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"{role_name.lower()}{suffix}",
        hashed_password=hash_password(password), first_name="Test", last_name=role_name,
        role_id=role.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user, password


async def _create_batch_with_upload(client: AsyncClient, headers: dict) -> str:
    resp = await client.post("/api/v1/migration/batches", json={"source_type": "CSV", "source_description": "pytest-sample"}, headers=headers)
    assert resp.status_code == 201, resp.text
    batch_id = resp.json()["id"]

    files = [
        ("files", ("patients.csv", PATIENTS_CSV, "text/csv")),
        ("files", ("doctors.csv", DOCTORS_CSV, "text/csv")),
    ]
    resp = await client.post(f"/api/v1/migration/batches/{batch_id}/upload", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    return batch_id


async def _apply_default_mappings(client: AsyncClient, batch_id: str, headers: dict) -> None:
    mappings = [
        {"entity_type": "Patients", "source_field": "id", "is_ignored": True},
        {"entity_type": "Patients", "source_field": "FName", "destination_field": "first_name"},
        {"entity_type": "Patients", "source_field": "LName", "destination_field": "last_name"},
        {"entity_type": "Patients", "source_field": "DOB", "destination_field": "birth_date", "transform_type": "DateFormat", "transform_config": {"source_format": "%Y-%m-%d"}},
        {"entity_type": "Patients", "source_field": "Gender", "destination_field": "gender"},
        {"entity_type": "Patients", "source_field": "CivilStatus", "destination_field": "civil_status"},
        {"entity_type": "Patients", "source_field": "Mobile", "destination_field": "mobile_number", "transform_type": "PhoneFormat"},
        {"entity_type": "Patients", "source_field": "Email", "destination_field": "email"},
        {"entity_type": "Doctors", "source_field": "id", "is_ignored": True},
        {"entity_type": "Doctors", "source_field": "FName", "destination_field": "first_name"},
        {"entity_type": "Doctors", "source_field": "LName", "destination_field": "last_name"},
        {"entity_type": "Doctors", "source_field": "Specialization", "destination_field": "specialization"},
        {"entity_type": "Doctors", "source_field": "Email", "destination_field": "email"},
    ]
    resp = await client.put(f"/api/v1/migration/batches/{batch_id}/mappings", json={"mappings": mappings}, headers=headers)
    assert resp.status_code == 200, resp.text


async def test_analyze_detects_fields(client: AsyncClient, make_clinic_with_owner):
    _, _, headers = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers)
    resp = await client.post(f"/api/v1/migration/batches/{batch_id}/analyze", headers=headers)
    assert resp.status_code == 200, resp.text
    schema = resp.json()
    assert set(schema["Patients"]) == {"id", "FName", "LName", "DOB", "Gender", "CivilStatus", "Mobile", "Email"}
    assert "FName" in schema["Doctors"]


async def test_mapping_suggestion_produces_sensible_defaults(client: AsyncClient, make_clinic_with_owner):
    _, _, headers = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/analyze", headers=headers)
    resp = await client.get(f"/api/v1/migration/batches/{batch_id}/mappings/suggest?entity_type=Patients", headers=headers)
    assert resp.status_code == 200, resp.text
    by_source = {row["source_field"]: row["destination_field"] for row in resp.json()}
    assert by_source["FName"] == "first_name"
    assert by_source["LName"] == "last_name"
    assert by_source["DOB"] == "birth_date"
    assert by_source["Mobile"] == "mobile_number"
    assert by_source["id"] is None  # no sensible destination - correctly left unmapped


async def test_validation_flags_broken_row_only(client: AsyncClient, make_clinic_with_owner):
    _, _, headers = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/analyze", headers=headers)
    await _apply_default_mappings(client, batch_id, headers)

    resp = await client.post(f"/api/v1/migration/batches/{batch_id}/validate?entity_type=Patients", headers=headers)
    assert resp.status_code == 200, resp.text
    issues = resp.json()
    flagged_rows = {i["source_row_identifier"] for i in issues}
    assert flagged_rows == {"3"}  # only the deliberately-broken row
    issue_types = {i["issue_type"] for i in issues if i["source_row_identifier"] == "3"}
    assert "RequiredFieldMissing" in issue_types  # missing birth_date/mobile_number


async def test_preview_computes_correct_counts(client: AsyncClient, make_clinic_with_owner):
    _, _, headers = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/analyze", headers=headers)
    await _apply_default_mappings(client, batch_id, headers)

    resp = await client.post(f"/api/v1/migration/batches/{batch_id}/preview?entity_type=Patients", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_to_import"] == 2
    assert body["rows_to_skip"] == 1
    assert body["errors"] == 1


async def _run_full_import(client: AsyncClient, db_session: AsyncSession, batch_id: str, headers: dict) -> None:
    resp = await client.post(f"/api/v1/migration/batches/{batch_id}/import", headers=headers)
    assert resp.status_code == 200, resp.text
    # Background task runs on the same event loop in the test ASGI transport;
    # give it a moment via direct await isn't available here, so poll status.
    import asyncio

    for _ in range(50):
        status_resp = await client.get(f"/api/v1/migration/batches/{batch_id}/status", headers=headers)
        body = status_resp.json()
        if body["batch"]["status"] in ("Completed", "PartiallyCompleted", "Failed"):
            return
        await asyncio.sleep(0.2)
    raise AssertionError("Import did not reach a terminal status in time")


async def test_import_creates_patients_and_doctors_with_legacy_fields(
    client: AsyncClient, db_session: AsyncSession, make_clinic_with_owner
):
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/analyze", headers=headers)
    await _apply_default_mappings(client, batch_id, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/validate?entity_type=Patients", headers=headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/validate?entity_type=Doctors", headers=headers)

    await _run_full_import(client, db_session, batch_id, headers)

    result = await db_session.execute(select(Patient).where(Patient.clinic_id == clinic.id))
    patients = result.scalars().all()
    assert len(patients) == 2  # the 2 valid rows; row 3 skipped (required-field error)
    for p in patients:
        assert p.legacy_id in ("1", "2")
        assert p.migration_batch_id == str(uuid.UUID(batch_id))
        assert p.imported_at is not None

    result = await db_session.execute(select(Doctor).where(Doctor.clinic_id == clinic.id))
    doctors = result.scalars().all()
    assert len(doctors) == 1
    assert doctors[0].legacy_id == "1"
    assert doctors[0].imported_at is not None


async def test_second_import_is_idempotent_no_duplicate_rows(
    client: AsyncClient, db_session: AsyncSession, make_clinic_with_owner
):
    """The single most important test in this file: re-running the exact
    same import must not create duplicate Patient/Doctor rows."""
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/analyze", headers=headers)
    await _apply_default_mappings(client, batch_id, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/validate?entity_type=Patients", headers=headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/validate?entity_type=Doctors", headers=headers)

    await _run_full_import(client, db_session, batch_id, headers)

    count_before = (await db_session.execute(
        select(func.count()).select_from(Patient).where(Patient.clinic_id == clinic.id)
    )).scalar_one()
    doctor_count_before = (await db_session.execute(
        select(func.count()).select_from(Doctor).where(Doctor.clinic_id == clinic.id)
    )).scalar_one()
    assert count_before == 2
    assert doctor_count_before == 1

    # Re-run the identical import (resume/re-trigger).
    await _run_full_import(client, db_session, batch_id, headers)

    count_after = (await db_session.execute(
        select(func.count()).select_from(Patient).where(Patient.clinic_id == clinic.id)
    )).scalar_one()
    doctor_count_after = (await db_session.execute(
        select(func.count()).select_from(Doctor).where(Doctor.clinic_id == clinic.id)
    )).scalar_one()

    assert count_after == count_before  # zero new rows created
    assert doctor_count_after == doctor_count_before


async def test_verification_report_matches_counts(client: AsyncClient, db_session: AsyncSession, make_clinic_with_owner):
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/analyze", headers=headers)
    await _apply_default_mappings(client, batch_id, headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/validate?entity_type=Patients", headers=headers)
    await client.post(f"/api/v1/migration/batches/{batch_id}/validate?entity_type=Doctors", headers=headers)
    await _run_full_import(client, db_session, batch_id, headers)

    resp = await client.get(f"/api/v1/migration/batches/{batch_id}/verify", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overall_ok"] is True
    entity_map = {e["entity_type"]: e for e in body["entities"]}
    assert entity_map["Patients"]["imported"] == 2
    assert entity_map["Doctors"]["imported"] == 1


async def test_role_gating_owner_and_administrator_only(client: AsyncClient, db_session: AsyncSession, make_clinic_with_owner):
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)

    resp = await client.get("/api/v1/migration/batches", headers=headers)
    assert resp.status_code == 200

    for role_name in ("Doctor", "Receptionist", "Cashier", "Laboratory"):
        user, password = await _make_role_login(db_session, clinic_id=clinic.id, role_name=role_name)
        token = await _login(client, user.email, password)
        resp = await client.get("/api/v1/migration/batches", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, f"{role_name} should be forbidden, got {resp.status_code}"


async def test_tenant_isolation(client: AsyncClient, db_session: AsyncSession, make_clinic_with_owner):
    clinic_a, _, headers_a = await _owner_headers(client, make_clinic_with_owner)
    batch_id = await _create_batch_with_upload(client, headers_a)

    _, _, headers_b = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.get(f"/api/v1/migration/batches/{batch_id}/status", headers=headers_b)
    assert resp.status_code == 404  # clinic B cannot see clinic A's batch

    resp = await client.get("/api/v1/migration/batches", headers=headers_b)
    assert resp.status_code == 200
    assert all(b["id"] != batch_id for b in resp.json())
