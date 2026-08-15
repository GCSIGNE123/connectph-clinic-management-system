"""Integration tests for Phase 16 (Production Hardening).

Covers: `/live` and `/ready` probes (no auth, `/ready` really checks DB
connectivity); the request-ID middleware attaching a traceable header to
every response, including error responses via the standardized error
envelope; department-list cache invalidation on update (proves it's a real
invalidation strategy, not a bare TTL that would serve stale data); and
file-upload validation rejecting an oversized/wrong-type consultation
attachment request.

Run with:
    DATABASE_URL=postgresql+asyncpg://clinic_user:clinic_password@localhost:5433/connectph_clinic_test \
        pytest app/tests/test_production_hardening.py -v
from `backend/` - never against `connectph_clinic` (see conftest.py's safety guard).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_clear_all
from app.models.role import Role

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    cache_clear_all()
    yield
    _memory_buckets.clear()
    cache_clear_all()


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/api/v1/auth/login", json={"email_or_username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, owner.email, password)
    return clinic, owner, {"Authorization": f"Bearer {token}"}


# --- Health / readiness / liveness ---


async def test_live_endpoint_no_auth_required(client: AsyncClient):
    response = await client.get("/api/v1/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "alive"
    assert "uptime_seconds" in body


async def test_ready_endpoint_reports_db_reachable(client: AsyncClient):
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "reachable"


async def test_ready_endpoint_returns_503_when_db_unreachable(client: AsyncClient, monkeypatch):
    """Manually simulates DB unavailability rather than actually taking the
    test database down (which would break every other test in this file/
    session) - patches AsyncSessionLocal used by the readiness probe to
    raise, proving the 503 path without touching real connectivity.
    """
    from app.api.v1 import health as health_module

    class _BrokenSession:
        async def __aenter__(self):
            raise ConnectionError("simulated DB outage")

        async def __aexit__(self, *args):
            return False

    def _broken_session_local():
        return _BrokenSession()

    monkeypatch.setattr(health_module, "AsyncSessionLocal", _broken_session_local)
    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["database"] == "unreachable"


# --- Request-ID middleware + standardized error envelope ---


async def test_request_id_header_present_and_traceable(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert "x-request-id" in response.headers
    request_id = response.headers["x-request-id"]
    assert len(request_id) > 10  # a real UUID string, not empty/placeholder


async def test_request_id_echoed_when_client_supplies_one(client: AsyncClient):
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "test-fixed-id-123"})
    assert response.headers["x-request-id"] == "test-fixed-id-123"


async def test_error_envelope_includes_detail_and_request_id_on_404(client: AsyncClient, make_clinic_with_owner):
    _, _, headers = await _owner_headers(client, make_clinic_with_owner)
    response = await client.get(
        "/api/v1/patients/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert response.status_code == 404
    body = response.json()
    assert "detail" in body
    assert "request_id" in body
    assert body["request_id"] == response.headers["x-request-id"]


async def test_error_envelope_includes_request_id_on_validation_error(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    body = response.json()
    assert isinstance(body["detail"], list)
    assert "request_id" in body


# --- Cache invalidation (departments list) ---


async def test_department_list_cache_invalidated_on_update(client: AsyncClient, make_clinic_with_owner):
    _, _, headers = await _owner_headers(client, make_clinic_with_owner)

    create_resp = await client.post(
        "/api/v1/departments", headers=headers,
        json={"department_code": "CACHE", "name": "Original Name"},
    )
    assert create_resp.status_code == 201, create_resp.text
    department_id = create_resp.json()["id"]

    # First read populates the cache.
    list_resp = await client.get("/api/v1/departments", headers=headers)
    assert list_resp.status_code == 200
    names = [item["name"] for item in list_resp.json()["items"]]
    assert "Original Name" in names

    # Update - must invalidate the cache immediately, not after a TTL wait.
    update_resp = await client.put(
        f"/api/v1/departments/{department_id}", headers=headers, json={"name": "Renamed Name"}
    )
    assert update_resp.status_code == 200

    # Immediate re-read (same test, no sleep) must reflect the rename - if
    # this were a bare TTL cache with no invalidation, this would still show
    # "Original Name" until the TTL expired, silently serving stale data.
    list_resp_after = await client.get("/api/v1/departments", headers=headers)
    names_after = [item["name"] for item in list_resp_after.json()["items"]]
    assert "Renamed Name" in names_after
    assert "Original Name" not in names_after


# --- File upload validation ---


async def test_consultation_attachment_upload_rejects_oversized_file(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
):
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    visit_id, consultation_id, doctor_headers = await _make_open_consultation(client, db_session, clinic, owner, headers)

    oversized = b"x" * (20 * 1024 * 1024 + 1)  # MAX_DOCUMENT_SIZE_BYTES + 1
    response = await client.post(
        f"/api/v1/consultations/{consultation_id}/attachments",
        headers=doctor_headers,
        data={"attachment_type": "PDF"},
        files={"file": ("scan.pdf", oversized, "application/pdf")},
    )
    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()


async def test_consultation_attachment_upload_rejects_disallowed_extension(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
):
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    visit_id, consultation_id, doctor_headers = await _make_open_consultation(client, db_session, clinic, owner, headers)

    response = await client.post(
        f"/api/v1/consultations/{consultation_id}/attachments",
        headers=doctor_headers,
        data={"attachment_type": "PDF"},
        files={"file": ("malware.exe", b"not-a-real-file", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()


async def test_consultation_attachment_upload_accepts_valid_file(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
):
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    visit_id, consultation_id, doctor_headers = await _make_open_consultation(client, db_session, clinic, owner, headers)

    response = await client.post(
        f"/api/v1/consultations/{consultation_id}/attachments",
        headers=doctor_headers,
        data={"attachment_type": "PDF"},
        files={"file": ("scan.pdf", b"%PDF-1.4 fake but nonzero", "application/pdf")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["file_name"] == "scan.pdf"
    # Feature 2: the returned file_url is a real, resolvable, authenticated
    # path (not the old presigned-URL-stub's fake stub.supabase.local URL).
    assert body["file_url"] == f"/consultations/{consultation_id}/attachments/{body['id']}/file"


# --- Feature 2: uploaded attachments are actually viewable afterward -------


# A real, valid, tiny (1x1 pixel) PNG - needed because the upload endpoint
# now validates/stores real bytes, not just declared metadata.
_TINY_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415478da6360000002000155a8f3580000000049454e44ae426082"
)


async def test_consultation_attachment_upload_and_view_image_immediately(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
):
    """Feature 2's core requirement: after a successful upload, the file is
    immediately retrievable and its bytes match what was uploaded - not a
    dead presigned-URL-stub link."""
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    visit_id, consultation_id, doctor_headers = await _make_open_consultation(client, db_session, clinic, owner, headers)

    upload = await client.post(
        f"/api/v1/consultations/{consultation_id}/attachments",
        headers=doctor_headers,
        data={"attachment_type": "ClinicalImage"},
        files={"file": ("wound.png", _TINY_PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    attachment = upload.json()

    # Shows up in the list immediately, with the same viewable file_url.
    listed = await client.get(f"/api/v1/consultations/{consultation_id}/attachments", headers=doctor_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["file_url"] == attachment["file_url"]

    fetched = await client.get(f"/api/v1{attachment['file_url']}", headers=doctor_headers)
    assert fetched.status_code == 200
    assert fetched.content == _TINY_PNG_BYTES
    assert fetched.headers["content-type"] == "image/png"


async def test_consultation_attachment_pdf_is_not_served_with_an_image_content_type(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
):
    """A non-image attachment must never be mistakenly treated as an
    image - the served content-type must reflect the real file type."""
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    visit_id, consultation_id, doctor_headers = await _make_open_consultation(client, db_session, clinic, owner, headers)

    upload = await client.post(
        f"/api/v1/consultations/{consultation_id}/attachments",
        headers=doctor_headers,
        data={"attachment_type": "PDF"},
        files={"file": ("referral.pdf", b"%PDF-1.4 fake but nonzero", "application/pdf")},
    )
    assert upload.status_code == 200, upload.text
    attachment = upload.json()
    assert attachment["attachment_type"] == "PDF"

    fetched = await client.get(f"/api/v1{attachment['file_url']}", headers=doctor_headers)
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "application/pdf"
    assert not fetched.headers["content-type"].startswith("image/")


async def test_consultation_attachment_file_requires_authentication(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
):
    """Preserves existing authorization: the real file is not reachable by
    an unauthenticated request, same as `list_attachments` already
    required a valid session."""
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    visit_id, consultation_id, doctor_headers = await _make_open_consultation(client, db_session, clinic, owner, headers)

    upload = await client.post(
        f"/api/v1/consultations/{consultation_id}/attachments",
        headers=doctor_headers,
        data={"attachment_type": "ClinicalImage"},
        files={"file": ("wound.png", _TINY_PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    file_url = upload.json()["file_url"]

    unauthenticated = await client.get(f"/api/v1{file_url}")
    assert unauthenticated.status_code == 401


async def _make_open_consultation(client, db_session, clinic, owner, headers):
    """Real Doctor login + a full Queue -> Visit -> open-consultation flow,
    reusing the same helper pattern as test_consultations.py, trimmed to
    just what this file's attachment tests need."""
    from app.core.security import hash_password
    import uuid as _uuid

    result = await db_session.execute(select(Role).where(Role.name == "Doctor"))
    doctor_role = result.scalar_one()

    branch_resp = await client.post(
        "/api/v1/branches", headers=headers, json={"name": "Main", "code": "MAIN"}
    )
    assert branch_resp.status_code == 201, branch_resp.text
    branch_id = branch_resp.json()["id"]

    dept_resp = await client.post(
        "/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General"}
    )
    assert dept_resp.status_code == 201, dept_resp.text
    department_id = dept_resp.json()["id"]

    doctor_resp = await client.post(
        "/api/v1/doctors", headers=headers,
        json={"first_name": "Test", "last_name": "Doctor", "department_id": department_id, "consultation_fee": 500},
    )
    assert doctor_resp.status_code == 201, doctor_resp.text
    doctor_id = doctor_resp.json()["id"]

    service_resp = await client.post(
        "/api/v1/services", headers=headers,
        json={"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": 500, "department_id": department_id},
    )
    assert service_resp.status_code == 201, service_resp.text
    service_id = service_resp.json()["id"]

    patient_resp = await client.post(
        "/api/v1/patients", headers=headers,
        json={
            "first_name": "Test", "last_name": "Patient", "birth_date": "1990-01-01",
            "gender": "Male", "civil_status": "Single", "mobile_number": "09171234567",
        },
    )
    assert patient_resp.status_code == 201, patient_resp.text
    patient_id = patient_resp.json()["patient"]["id"]

    suffix = _uuid.uuid4().hex[:8]
    doctor_email = f"doctor-{suffix}@example.com"
    from app.models.user import User

    user = User(
        clinic_id=clinic.id, email=doctor_email, username=f"doctor{suffix}",
        hashed_password=hash_password("DoctorPass123!"), first_name="Test", last_name="Doctor",
        role_id=doctor_role.id, doctor_id=doctor_id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    doctor_token = await _login(client, doctor_email, "DoctorPass123!")
    doctor_headers = {"Authorization": f"Bearer {doctor_token}"}

    queue_resp = await client.post(
        "/api/v1/queues", headers=headers,
        json={
            "patient_id": patient_id, "branch_id": branch_id, "department_id": department_id,
            "doctor_id": doctor_id, "service_id": service_id, "priority": "Normal",
        },
    )
    assert queue_resp.status_code == 201, queue_resp.text
    visit_id = queue_resp.json()["visit_id"]

    call_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doctor_headers)
    assert call_resp.status_code == 200, call_resp.text
    start_resp = await client.post(
        f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doctor_headers
    )
    assert start_resp.status_code == 200, start_resp.text

    open_resp = await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doctor_headers)
    assert open_resp.status_code == 200, open_resp.text
    consultation_id = open_resp.json()["id"]
    return visit_id, consultation_id, doctor_headers
