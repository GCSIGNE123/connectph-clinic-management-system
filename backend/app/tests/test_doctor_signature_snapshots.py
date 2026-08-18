"""Doctor E-Signature snapshot behavior: Prescription/Referral/Medical
Certificate capture the doctor's CURRENT signature at issuance time, and a
later signature replacement on the Doctor record must never alter an
already-issued document's rendering (product decision - a deliberate,
scoped exception to this codebase's live-join convention for doctor
identity fields elsewhere).
"""

import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.role import Role

pytestmark = pytest.mark.asyncio

PNG_V1 = b"\x89PNG\r\n\x1a\n" + b"V1-SIGNATURE-BYTES"
PNG_V2 = b"\x89PNG\r\n\x1a\n" + b"V2-REPLACEMENT-BYTES"


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


async def _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session):
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


async def _upload_signature(client, owner_headers, doctor_id, content: bytes) -> str:
    resp = await client.post(
        f"/api/v1/doctors/{doctor_id}/signature", headers=owner_headers,
        files={"file": ("sig.png", io.BytesIO(content), "image/png")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["signature_url"]


# --- Prescription ---


async def test_prescription_snapshots_doctor_signature_at_creation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)
    signature_url = await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V1)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers,
        json={"items": [{"medicine": "Amoxicillin", "dosage": "500mg", "duration": "7 days"}]},
    )
    assert resp.status_code == 200, resp.text
    prescription = resp.json()["prescription"]
    assert prescription["doctor_signature_snapshot_url"] == signature_url

    file_resp = await client.get(f"/api/v1/prescriptions/{prescription['id']}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_V1


async def test_prescription_created_before_signature_upload_has_no_snapshot(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers,
        json={"items": [{"medicine": "Amoxicillin", "dosage": "500mg", "duration": "7 days"}]},
    )
    assert resp.status_code == 200, resp.text
    prescription = resp.json()["prescription"]
    assert prescription["doctor_signature_snapshot_url"] is None

    file_resp = await client.get(f"/api/v1/prescriptions/{prescription['id']}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 404


async def test_prescription_snapshot_unchanged_after_doctor_signature_replaced(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)
    await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V1)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers,
        json={"items": [{"medicine": "Amoxicillin", "dosage": "500mg", "duration": "7 days"}]},
    )
    prescription_id = resp.json()["prescription"]["id"]

    # Replace the doctor's CURRENT signature after the prescription exists.
    await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V2)

    # Old prescription's snapshot file must still resolve to the ORIGINAL bytes.
    file_resp = await client.get(f"/api/v1/prescriptions/{prescription_id}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_V1

    # The doctor's current signature is now V2.
    current_doctor = (await client.get(f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers)).json()
    current_file = await client.get(f"/api/v1/doctors/{deps['doctor_id']}/signature/file", headers=owner_headers)
    assert current_doctor["signature_url"] is not None
    assert current_file.content == PNG_V2


# --- Referral ---


async def test_referral_snapshots_doctor_signature_at_creation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)
    signature_url = await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V1)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/referrals", headers=doc_headers,
        json={"referred_to": "Dr. Cardio Specialist", "reason": "Chest pain evaluation"},
    )
    assert resp.status_code == 200, resp.text
    referral = resp.json()
    assert referral["doctor_signature_snapshot_url"] == signature_url

    file_resp = await client.get(f"/api/v1/referrals/{referral['id']}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_V1


async def test_referral_snapshot_unchanged_after_doctor_signature_replaced(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)
    await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V1)

    resp = await client.post(
        f"/api/v1/consultations/{cid}/referrals", headers=doc_headers,
        json={"referred_to": "Dr. Cardio Specialist", "reason": "Chest pain evaluation"},
    )
    referral_id = resp.json()["id"]

    await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V2)

    file_resp = await client.get(f"/api/v1/referrals/{referral_id}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_V1


# --- Medical Certificate ---


async def test_medical_certificate_snapshots_doctor_signature_at_issue(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)
    signature_url = await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V1)

    draft = (
        await client.post(
            f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers,
            json={"certificate_type": "MedicalCertificate", "findings": "URTI", "recommendation": "Rest"},
        )
    ).json()
    # Draft (not yet issued) has no signature snapshot yet.
    assert draft["doctor_signature_snapshot_url"] is None

    issued = (await client.post(f"/api/v1/medical-certificates/{draft['id']}/issue", headers=doc_headers)).json()
    assert issued["doctor_signature_snapshot_url"] == signature_url

    file_resp = await client.get(f"/api/v1/medical-certificates/{issued['id']}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_V1


async def test_medical_certificate_issued_with_no_signature_configured_prints_blank(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """No fabricated signature: a doctor with none configured can still
    issue a certificate; print just shows a blank signature area."""
    _clinic, _owner_headers, doc_headers, _deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)

    draft = (
        await client.post(
            f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers,
            json={"certificate_type": "MedicalCertificate", "findings": "URTI", "recommendation": "Rest"},
        )
    ).json()
    issue_resp = await client.post(f"/api/v1/medical-certificates/{draft['id']}/issue", headers=doc_headers)
    assert issue_resp.status_code == 200, issue_resp.text
    issued = issue_resp.json()
    assert issued["doctor_signature_snapshot_url"] is None

    file_resp = await client.get(f"/api/v1/medical-certificates/{issued['id']}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 404


async def test_medical_certificate_snapshot_unchanged_after_doctor_signature_replaced(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, doc_headers, deps, _visit_id, cid = await _setup_doctor_and_consultation(client, make_clinic_with_owner, db_session)
    await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V1)

    draft = (
        await client.post(
            f"/api/v1/consultations/{cid}/medical-certificates", headers=doc_headers,
            json={"certificate_type": "MedicalCertificate", "findings": "URTI", "recommendation": "Rest"},
        )
    ).json()
    issued = (await client.post(f"/api/v1/medical-certificates/{draft['id']}/issue", headers=doc_headers)).json()

    # Replace, then even REMOVE the doctor's current signature entirely.
    await _upload_signature(client, owner_headers, deps["doctor_id"], PNG_V2)
    await client.delete(f"/api/v1/doctors/{deps['doctor_id']}/signature", headers=owner_headers)

    file_resp = await client.get(f"/api/v1/medical-certificates/{issued['id']}/signature/file", headers=doc_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_V1

    current_doctor = (await client.get(f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers)).json()
    assert current_doctor["signature_url"] is None
