"""Integration tests for Phase 8 Clinical Consultation / SOAP: open creates
Draft + acquires lock + timeline event, SOAP autosave upserts (not
duplicates) and computes BMI, Draft->InProgress transition, diagnosis
add with timeline+audit, complete-consultation Visit-status sync (the
critical Phase-7-lesson interaction), sign, locking (second doctor/admin
view-only, receptionist 403 on both view and edit), autosave idempotency
(no timeline spam), previous-consultation read-only retrieval, and tenant
isolation.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.role import Role

pytestmark = pytest.mark.asyncio


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


async def _setup_queue_deps(client: AsyncClient, headers: dict) -> dict:
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General Medicine"})
    ).json()
    doctor = (await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Jose", "last_name": "Rizal"})).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": "500.00"},
        )
    ).json()
    patient = (
        await client.post(
            "/api/v1/patients", headers=headers,
            json={
                "first_name": "Juan", "last_name": "Dela Cruz", "birth_date": "1990-05-15",
                "gender": "Male", "civil_status": "Single", "mobile_number": "+639171234567",
            },
        )
    ).json()["patient"]
    return {
        "branch_id": branch["id"], "department_id": department["id"],
        "doctor_id": doctor["id"], "service_id": service["id"], "patient_id": patient["id"],
    }


def _queue_payload(deps: dict, **overrides) -> dict:
    payload = {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
        "department_id": deps["department_id"], "doctor_id": deps["doctor_id"],
        "service_id": deps["service_id"], "priority": "Normal",
    }
    payload.update(overrides)
    return payload


async def _make_doctor_login(db_session: AsyncSession, *, clinic_id, doctor_id, password: str = "DoctorPass123!"):
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == "Doctor"))
    doctor_role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"doc-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"doc{suffix}", hashed_password=hash_password(password),
        first_name="Test", last_name="Doctor", role_id=doctor_role.id, doctor_id=doctor_id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return email, user


async def _make_receptionist_login(db_session: AsyncSession, *, clinic_id, password: str = "ReceptPass123!"):
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == "Receptionist"))
    role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"rec-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"rec{suffix}", hashed_password=hash_password(password),
        first_name="Test", last_name="Reception", role_id=role.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return email, user


async def _create_visit(client, headers, deps) -> dict:
    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    assert queue.get("visit_id"), queue
    return queue


async def _advance_to_in_consultation(client, doc_headers, visit_id) -> None:
    r1 = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    assert r1.status_code == 200, r1.text
    r2 = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    assert r2.status_code == 200, r2.text


async def _setup_doctor_and_visit(client, make_clinic_with_owner, db_session):
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await _advance_to_in_consultation(client, doc_headers, visit_id)
    return clinic, owner_headers, doc_headers, deps, visit_id


async def test_open_consultation_creates_draft_lock_and_timeline(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)

    resp = await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Draft"
    assert body["lock"]["locked"] is True
    assert body["lock"]["is_self"] is True

    timeline = await client.get(f"/api/v1/consultations/{body['id']}/timeline", headers=doc_headers)
    assert timeline.status_code == 200, timeline.text
    event_types = [e["event_type"] for e in timeline.json()["events"]]
    assert "ConsultationOpened" in event_types


async def test_save_soap_upserts_and_computes_bmi_and_bumps_status(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]
    assert opened["status"] == "Draft"

    payload = {"chief_complaint": "Fever", "height_cm": 160, "weight_kg": 64}
    resp1 = await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json=payload)
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert body1["status"] == "InProgress"
    assert body1["soap_note"]["bmi"] == pytest.approx(25.0, rel=0.01)

    # Second save with updated content should upsert the SAME soap_note row, not create a new one.
    resp2 = await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json={**payload, "chief_complaint": "Fever and cough"})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["soap_note"]["id"] == body1["soap_note"]["id"]
    assert body2["soap_note"]["chief_complaint"] == "Fever and cough"


async def test_autosave_idempotent_no_timeline_spam(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    payload = {"chief_complaint": "Fever", "height_cm": 160, "weight_kg": 64}
    for _ in range(4):
        resp = await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json=payload)
        assert resp.status_code == 200

    timeline = await client.get(f"/api/v1/consultations/{cid}/timeline", headers=doc_headers)
    soap_saved_count = sum(1 for e in timeline.json()["events"] if e["event_type"] == "SoapSaved")
    assert soap_saved_count == 1, "Repeated identical autosave payloads must not spam the timeline"


async def test_add_diagnosis_primary_and_secondary(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    resp = await client.post(
        f"/api/v1/consultations/{cid}/diagnoses", headers=doc_headers,
        json={"diagnosis_type": "Primary", "status": "Working", "notes": "URTI", "icd10_code": "J06.9"},
    )
    assert resp.status_code == 200, resp.text
    diagnoses = resp.json()["diagnoses"]
    assert len(diagnoses) == 1
    assert diagnoses[0]["diagnosis_type"] == "Primary"

    resp2 = await client.post(
        f"/api/v1/consultations/{cid}/diagnoses", headers=doc_headers,
        json={"diagnosis_type": "Secondary", "status": "Working", "notes": "Mild dehydration"},
    )
    assert len(resp2.json()["diagnoses"]) == 2

    timeline = await client.get(f"/api/v1/consultations/{cid}/timeline", headers=doc_headers)
    assert sum(1 for e in timeline.json()["events"] if e["event_type"] == "DiagnosisAdded") == 2


async def test_complete_consultation_reflects_onto_visit_status(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """The critical Phase-7-lesson check: completing a Consultation must not
    leave Visit.status silently stuck at InConsultation."""
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]
    await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json={"chief_complaint": "Fever"})

    visit_before = await client.get(f"/api/v1/visits/{visit_id}", headers=doc_headers)
    assert visit_before.json()["status"] == "InConsultation"

    resp = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Completed"

    visit_after = await client.get(f"/api/v1/visits/{visit_id}", headers=doc_headers)
    assert visit_after.json()["status"] == "Completed", "Visit.status must sync to Completed when a Consultation completes"

    # Idempotent: completing again (e.g. Doctor Workspace already completed
    # the Visit independently) must not error.
    resp2 = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "Completed"


async def test_sign_consultation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]
    await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json={"chief_complaint": "Fever"})
    await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)

    resp = await client.post(f"/api/v1/consultations/{cid}/sign", headers=doc_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "Signed"

    # Cannot edit SOAP after signing.
    edit_resp = await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json={"chief_complaint": "changed"})
    assert edit_resp.status_code == 400


async def test_locking_second_doctor_and_admin_view_only(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    # Second, unrelated doctor: can view (403 is not expected - Doctor role
    # passes the view gate) but cannot edit (not the assigned doctor).
    doctor2 = (await client.post("/api/v1/doctors", headers=owner_headers, json={"first_name": "Ana", "last_name": "Lopez"})).json()
    doc2_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=doctor2["id"])
    doc2_token = await _login(client, doc2_email, "DoctorPass123!")
    doc2_headers = {"Authorization": f"Bearer {doc2_token}"}

    view_resp = await client.get(f"/api/v1/consultations/{cid}", headers=doc2_headers)
    assert view_resp.status_code == 200
    edit_resp = await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc2_headers, json={"chief_complaint": "x"})
    assert edit_resp.status_code == 403

    # Administrator: view-only, never edit, per spec (stricter than Phase 7).
    admin_view = await client.get(f"/api/v1/consultations/{cid}", headers=owner_headers)
    assert admin_view.status_code == 200
    admin_edit = await client.put(f"/api/v1/consultations/{cid}/soap", headers=owner_headers, json={"chief_complaint": "x"})
    assert admin_edit.status_code == 403


async def test_receptionist_forbidden_view_and_edit(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    rec_email, _ = await _make_receptionist_login(db_session, clinic_id=clinic.id)
    rec_token = await _login(client, rec_email, "ReceptPass123!")
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    view_resp = await client.get(f"/api/v1/consultations/{cid}", headers=rec_headers)
    assert view_resp.status_code == 403

    edit_resp = await client.put(f"/api/v1/consultations/{cid}/soap", headers=rec_headers, json={"chief_complaint": "x"})
    assert edit_resp.status_code == 403


async def test_previous_consultation_readonly_retrieval(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]
    await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json={"chief_complaint": "Fever"})
    await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    await client.post(f"/api/v1/consultations/{cid}/sign", headers=doc_headers)

    resp = await client.get(f"/api/v1/consultations/{cid}", headers=doc_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "Signed"
    assert body["soap_note"]["chief_complaint"] == "Fever"


async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic1, _owner1, doc1_headers, _deps1, visit1_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened1 = (await client.post(f"/api/v1/visits/{visit1_id}/consultation/open", headers=doc1_headers)).json()
    cid1 = opened1["id"]

    _clinic2, _owner2, doc2_headers, _deps2, _visit2_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)

    resp = await client.get(f"/api/v1/consultations/{cid1}", headers=doc2_headers)
    assert resp.status_code in (403, 404)
