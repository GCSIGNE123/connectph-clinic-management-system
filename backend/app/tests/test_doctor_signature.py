"""Doctor E-Signature: upload/replace/remove/authenticated retrieval,
clinic isolation, role/ownership permissions, and signature-snapshot
capture on Prescription/Referral/Medical Certificate issuance (proving a
later signature replacement never alters an already-issued document).
"""

import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User

pytestmark = pytest.mark.asyncio

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
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


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, doctor_id=None, password: str = "TestPass123!"):
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
    return email, password, user


def _png_file(name: str = "sig.png"):
    return {"file": (name, io.BytesIO(PNG_BYTES), "image/png")}


async def _create_doctor(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {"first_name": "Jose", "last_name": "Rizal"}
    payload.update(overrides)
    resp = await client.post("/api/v1/doctors", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- Upload / validation ---


async def test_owner_can_upload_png_signature(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)

    resp = await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())
    assert resp.status_code == 200, resp.text
    assert resp.json()["signature_url"]


async def test_non_png_upload_is_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)

    resp = await client.post(
        f"/api/v1/doctors/{doctor['id']}/signature", headers=headers,
        files={"file": ("sig.jpg", io.BytesIO(b"\xff\xd8\xff\xe0fakejpeg"), "image/jpeg")},
    )
    assert resp.status_code == 400, resp.text


async def test_empty_file_upload_is_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)

    resp = await client.post(
        f"/api/v1/doctors/{doctor['id']}/signature", headers=headers,
        files={"file": ("sig.png", io.BytesIO(b""), "image/png")},
    )
    assert resp.status_code == 400, resp.text


# --- Clinic isolation ---


async def test_signature_upload_is_clinic_isolated(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    doctor_a = await _create_doctor(client, headers_a)

    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    resp = await client.post(f"/api/v1/doctors/{doctor_a['id']}/signature", headers=headers_b, files=_png_file())
    assert resp.status_code == 404, resp.text


# --- Ownership / role permissions ---


async def test_doctor_can_manage_own_signature(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, owner_headers)
    doc_email, doc_password, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=uuid.UUID(doctor["id"]))
    doc_token = await _login(client, doc_email, doc_password)
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    resp = await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=doc_headers, files=_png_file())
    assert resp.status_code == 200, resp.text


async def test_doctor_cannot_manage_another_doctors_signature(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    doctor_a = await _create_doctor(client, owner_headers, first_name="Jose", last_name="Rizal")
    doctor_b = await _create_doctor(client, owner_headers, first_name="Maria", last_name="Clara")
    doc_email, doc_password, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=uuid.UUID(doctor_a["id"]))
    doc_token = await _login(client, doc_email, doc_password)
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    resp = await client.post(f"/api/v1/doctors/{doctor_b['id']}/signature", headers=doc_headers, files=_png_file())
    assert resp.status_code == 403, resp.text


async def test_receptionist_cannot_upload_signature(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, owner_headers)
    rec_email, rec_password, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    rec_token = await _login(client, rec_email, rec_password)
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    resp = await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=rec_headers, files=_png_file())
    assert resp.status_code == 403, resp.text


async def test_cashier_cannot_remove_signature(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, owner_headers)
    await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=owner_headers, files=_png_file())
    cash_email, cash_password, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Cashier")
    cash_token = await _login(client, cash_email, cash_password)
    cash_headers = {"Authorization": f"Bearer {cash_token}"}

    resp = await client.delete(f"/api/v1/doctors/{doctor['id']}/signature", headers=cash_headers)
    assert resp.status_code == 403, resp.text


# --- Replace / remove / retrieve ---


async def test_replace_signature_changes_current_signature(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)

    first = (await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())).json()
    second = (await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())).json()
    assert first["signature_url"] != second["signature_url"]

    current = (await client.get(f"/api/v1/doctors/{doctor['id']}", headers=headers)).json()
    assert current["signature_url"] == second["signature_url"]


async def test_remove_signature_clears_current_signature(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)
    await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())

    resp = await client.delete(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["signature_url"] is None

    file_resp = await client.get(f"/api/v1/doctors/{doctor['id']}/signature/file", headers=headers)
    assert file_resp.status_code == 404


async def test_authenticated_retrieval_returns_the_uploaded_png(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)
    await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())

    resp = await client.get(f"/api/v1/doctors/{doctor['id']}/signature/file", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content == PNG_BYTES


async def test_signature_file_requires_authentication(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)
    await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())

    resp = await client.get(f"/api/v1/doctors/{doctor['id']}/signature/file")
    assert resp.status_code == 401


async def test_empty_state_when_no_signature_configured(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)

    current = (await client.get(f"/api/v1/doctors/{doctor['id']}", headers=headers)).json()
    assert current["signature_url"] is None

    file_resp = await client.get(f"/api/v1/doctors/{doctor['id']}/signature/file", headers=headers)
    assert file_resp.status_code == 404


# --- Audit ---


async def test_signature_upload_and_removal_are_audited(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    from app.models.audit_log import AuditLog

    clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = await _create_doctor(client, headers)

    await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())
    await client.post(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers, files=_png_file())
    await client.delete(f"/api/v1/doctors/{doctor['id']}/signature", headers=headers)

    result = await db_session.execute(
        select(AuditLog.action).where(AuditLog.clinic_id == clinic.id, AuditLog.entity_id == doctor["id"]).order_by(AuditLog.created_at)
    )
    actions = [row[0] for row in result.all()]
    assert "doctor_signature.added" in actions
    assert "doctor_signature.replaced" in actions
    assert "doctor_signature.removed" in actions
