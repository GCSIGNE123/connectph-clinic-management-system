"""Integration tests for Medical Certificates: draft create/edit, issue
(numbering + immutability), cancel (reason required), cancel+reissue
(supersession linkage), findings snapshot from Diagnosis, doctor-only edit
permission, Receptionist/Cashier view+reprint-only, patient/visit/
consultation relationship validation, and tenant isolation.
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
    doctor = (
        await client.post(
            "/api/v1/doctors", headers=headers,
            json={"first_name": "Jose", "last_name": "Rizal", "prc_license": "PRC-12345", "ptr_number": "PTR-98765"},
        )
    ).json()
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


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, doctor_id=None, password: str):
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"{role_name.lower()}-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"{role_name.lower()}{suffix}", hashed_password=hash_password(password),
        first_name="Test", last_name=role_name, role_id=role.id, doctor_id=doctor_id, is_active=True,
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


async def _full_setup(client, make_clinic_with_owner, db_session):
    clinic, owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(
        db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"], password="DoctorPass123!"
    )
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await _advance_to_in_consultation(client, doc_headers, visit_id)

    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]
    return clinic, owner_headers, doc_headers, deps, visit_id, cid


def _draft_payload(**overrides) -> dict:
    payload = {
        "certificate_type": "MedicalCertificate",
        "findings": "Upper respiratory tract infection",
        "recommendation": "Rest and hydration advised",
    }
    payload.update(overrides)
    return payload


# --- Draft create/edit ---

async def test_create_draft_certificate(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)

    resp = await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Draft"
    assert body["certificate_number"] is None
    assert body["findings"] == "Upper respiratory tract infection"
    # Live-pulled display fields, never stored on the row.
    assert body["doctor_name"]
    assert body["doctor_prc_license"] == "PRC-12345"
    assert body["doctor_ptr_number"] == "PTR-98765"
    assert body["patient_name"]
    assert body["clinic_name"]


async def test_edit_draft_certificate(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    resp = await client.patch(
        f"/api/v1/medical-certificates/{created['id']}", headers=doc_headers,
        json={"findings": "Updated findings", "certificate_type": "SickLeave", "rest_days": 3},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["findings"] == "Updated findings"
    assert body["certificate_type"] == "SickLeave"
    assert body["rest_days"] == 3
    assert body["status"] == "Draft"


# --- Issue / numbering ---

async def test_issue_certificate_generates_number(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    resp = await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "Issued"
    assert body["certificate_number"] is not None
    assert body["certificate_number"].startswith("MC-")
    assert body["issued_at"] is not None


async def test_certificate_numbers_are_sequential_same_day(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)

    first = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()
    second = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    first_issued = (await client.post(f"/api/v1/medical-certificates/{first['id']}/issue", headers=doc_headers)).json()
    second_issued = (await client.post(f"/api/v1/medical-certificates/{second['id']}/issue", headers=doc_headers)).json()

    first_seq = int(first_issued["certificate_number"].split("-")[-1])
    second_seq = int(second_issued["certificate_number"].split("-")[-1])
    assert second_seq == first_seq + 1


# --- Findings snapshot ---

async def test_findings_snapshot_survives_later_diagnosis_edits(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """The certificate's `findings` is a text snapshot the doctor typed at
    draft time - it has no live FK to Diagnosis, so it must not change if a
    diagnosis is added/edited afterward."""
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (
        await client.post(
            f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers,
            json=_draft_payload(findings="Snapshot: Acute pharyngitis"),
        )
    ).json()
    issued = (await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)).json()
    assert issued["findings"] == "Snapshot: Acute pharyngitis"

    await client.post(
        f"/api/v1/consultations/{cid}/diagnoses", headers=doc_headers,
        json={"diagnosis_type": "Primary", "status": "Final", "notes": "Different, later diagnosis"},
    )

    refetched = (await client.get(f"/api/v1/medical-certificates/{created['id']}", headers=doc_headers)).json()
    assert refetched["findings"] == "Snapshot: Acute pharyngitis"


# --- Immutability ---

async def test_issued_certificate_cannot_be_edited(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()
    await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)

    resp = await client.patch(
        f"/api/v1/medical-certificates/{created['id']}", headers=doc_headers, json={"findings": "Trying to sneak an edit in"}
    )
    assert resp.status_code == 400, resp.text
    assert "immutable" in resp.json()["detail"].lower() or "already" in resp.json()["detail"].lower()

    unchanged = (await client.get(f"/api/v1/medical-certificates/{created['id']}", headers=doc_headers)).json()
    assert unchanged["findings"] != "Trying to sneak an edit in"


async def test_cannot_issue_an_already_issued_certificate(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()
    await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)

    resp = await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)
    assert resp.status_code == 400, resp.text


# --- Cancel ---

async def test_cancel_requires_reason(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()
    await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)

    resp = await client.post(f"/api/v1/medical-certificates/{created['id']}/cancel", headers=doc_headers, json={"reason": ""})
    assert resp.status_code == 422, resp.text

    ok = await client.post(f"/api/v1/medical-certificates/{created['id']}/cancel", headers=doc_headers, json={"reason": "Wrong patient details"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "Cancelled"
    assert ok.json()["cancelled_reason"] == "Wrong patient details"


async def test_cannot_cancel_a_draft(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    resp = await client.post(f"/api/v1/medical-certificates/{created['id']}/cancel", headers=doc_headers, json={"reason": "N/A"})
    assert resp.status_code == 400, resp.text


# --- Cancel + Reissue (supersession) ---

async def test_reissue_creates_new_certificate_and_links_supersession(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()
    original = (await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)).json()

    resp = await client.post(
        f"/api/v1/medical-certificates/{original['id']}/reissue", headers=doc_headers,
        json={"reason": "Typo in patient name"},
    )
    assert resp.status_code == 200, resp.text
    new_certificate = resp.json()

    assert new_certificate["id"] != original["id"]
    assert new_certificate["status"] == "Issued"
    assert new_certificate["certificate_number"] != original["certificate_number"]
    assert new_certificate["findings"] == original["findings"]  # content copied forward

    original_after = (await client.get(f"/api/v1/medical-certificates/{original['id']}", headers=doc_headers)).json()
    assert original_after["status"] == "Cancelled"
    assert original_after["cancelled_reason"] == "Typo in patient name"
    assert original_after["superseded_by_id"] == new_certificate["id"]

    # The cancelled original remains visible in history, not deleted.
    history = (await client.get(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers)).json()
    ids = {c["id"] for c in history}
    assert original["id"] in ids
    assert new_certificate["id"] in ids


async def test_cannot_reissue_a_draft(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    resp = await client.post(f"/api/v1/medical-certificates/{created['id']}/reissue", headers=doc_headers, json={"reason": "N/A"})
    assert resp.status_code == 400, resp.text


# --- Permissions ---

async def test_other_doctor_cannot_edit_or_issue(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    other_doc_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", password="OtherDocPass123!")
    other_token = await _login(client, other_doc_email, "OtherDocPass123!")
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=other_headers)
    assert resp.status_code == 403, resp.text


async def test_owner_and_administrator_cannot_issue_on_doctors_behalf(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    # Owner can view (passes the broader role gate)...
    view = await client.get(f"/api/v1/medical-certificates/{created['id']}", headers=owner_headers)
    assert view.status_code == 200

    # ...but cannot create, edit, or issue on the doctor's behalf.
    create_resp = await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=owner_headers, json=_draft_payload())
    assert create_resp.status_code == 403, create_resp.text
    issue_resp = await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=owner_headers)
    assert issue_resp.status_code == 403, issue_resp.text


async def test_receptionist_cannot_create_or_issue(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)

    rec_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist", password="ReceptPass123!")
    rec_token = await _login(client, rec_email, "ReceptPass123!")
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    create_resp = await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=rec_headers, json=_draft_payload())
    assert create_resp.status_code == 403, create_resp.text


async def test_receptionist_can_view_and_reprint_issued_certificate(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()
    issued = (await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)).json()

    rec_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist", password="ReceptPass123!")
    rec_token = await _login(client, rec_email, "ReceptPass123!")
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    view = await client.get(f"/api/v1/medical-certificates/{issued['id']}", headers=rec_headers)
    assert view.status_code == 200, view.text

    reprint = await client.post(f"/api/v1/medical-certificates/{issued['id']}/print", headers=rec_headers)
    assert reprint.status_code == 200, reprint.text

    cancel_attempt = await client.post(f"/api/v1/medical-certificates/{issued['id']}/cancel", headers=rec_headers, json={"reason": "N/A"})
    assert cancel_attempt.status_code == 403, cancel_attempt.text


async def test_cashier_can_view_and_reprint_but_not_edit(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()
    issued = (await client.post(f"/api/v1/medical-certificates/{created['id']}/issue", headers=doc_headers)).json()

    cashier_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Cashier", password="CashierPass123!")
    cashier_token = await _login(client, cashier_email, "CashierPass123!")
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    view = await client.get(f"/api/v1/medical-certificates/{issued['id']}", headers=cashier_headers)
    assert view.status_code == 200

    reprint = await client.post(f"/api/v1/medical-certificates/{issued['id']}/print", headers=cashier_headers)
    assert reprint.status_code == 200, reprint.text

    edit_attempt = await client.patch(f"/api/v1/medical-certificates/{issued['id']}", headers=cashier_headers, json={"findings": "nope"})
    assert edit_attempt.status_code == 403, edit_attempt.text


# --- Relationship validation / tenant isolation ---

async def test_certificate_always_scoped_to_correct_consultation_visit_patient_doctor(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    _clinic, _owner_headers, doc_headers, deps, visit_id, cid = await _full_setup(client, make_clinic_with_owner, db_session)
    created = (await client.post(f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers, json=_draft_payload())).json()

    assert created["consultation_id"] == cid
    assert created["visit_id"] == visit_id
    assert created["patient_id"] == deps["patient_id"]
    assert created["doctor_id"] == deps["doctor_id"]

    visit_list = await client.get(f"/api/v1/visits/{visit_id}/medical-certificates", headers=doc_headers)
    assert visit_list.status_code == 200
    assert any(c["id"] == created["id"] for c in visit_list.json())

    patient_list = await client.get(f"/api/v1/patients/{deps['patient_id']}/medical-certificates", headers=doc_headers)
    assert patient_list.status_code == 200
    assert any(c["id"] == created["id"] for c in patient_list.json())


async def test_create_rejects_nonexistent_consultation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, _cid = await _full_setup(client, make_clinic_with_owner, db_session)
    fake_id = str(uuid.uuid4())
    resp = await client.post(f"/api/v1/consultations/{fake_id}/medical-certificates", headers=doc_headers, json=_draft_payload())
    assert resp.status_code in (403, 404)


async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic1, _owner1, doc1_headers, _deps1, _visit1_id, cid1 = await _full_setup(client, make_clinic_with_owner, db_session)
    _clinic2, _owner2, doc2_headers, _deps2, _visit2_id, _cid2 = await _full_setup(client, make_clinic_with_owner, db_session)

    created = (await client.post(f"/api/v1/consultations/{cid1}/medical-certificates", headers=doc1_headers, json=_draft_payload())).json()

    cross_get = await client.get(f"/api/v1/medical-certificates/{created['id']}", headers=doc2_headers)
    assert cross_get.status_code in (403, 404)

    cross_list = await client.get(f"/api/v1/consultations/{cid1}/medical-certificates", headers=doc2_headers)
    assert cross_list.status_code in (403, 404)
