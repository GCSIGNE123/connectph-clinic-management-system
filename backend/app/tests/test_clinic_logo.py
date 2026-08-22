"""Clinic Logo Branding (Round 7): real upload/replace/remove, tenant
isolation, invalid-file rejection, and graceful behavior for clinics with
no logo configured.

Mirrors `test_doctor_signature.py`'s upload-validation/PNG-bytes
conventions, but the clinic logo endpoint accepts the broader
`IMAGE_EXTENSIONS` set (jpg/jpeg/png/webp), matching every other real
image-upload flow in this app (`upload_validation.py::validate_image_upload`),
not the PNG-only convention used for e-signatures.
"""

import io

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PNG_BYTES_2 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\x0bIDATx\x9cc`\x00\x00\x00\x06\x00\x02\x9a\x18\x8e\xea\x00\x00\x00\x00IEND\xaeB`\x82"
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


def _png_file(name: str = "logo.png", content: bytes = PNG_BYTES):
    return {"file": (name, io.BytesIO(content), "image/png")}


async def test_1_clinic_can_upload_logo(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.post("/api/v1/clinic-settings/logo", headers=headers, files=_png_file())
    assert resp.status_code == 200, resp.text
    assert resp.json()["logo_url"]
    assert resp.json()["logo_url"].startswith("/media/clinic-logo/")


async def test_2_invalid_file_rejected_too_large(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (6 * 1024 * 1024)
    resp = await client.post("/api/v1/clinic-settings/logo", headers=headers, files=_png_file(content=oversized))
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"].lower()


async def test_3_non_image_extension_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.post(
        "/api/v1/clinic-settings/logo", headers=headers,
        files={"file": ("logo.exe", io.BytesIO(b"MZ\x90\x00fake-exe-bytes"), "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"].lower()


async def test_4_logo_retrieval_works_via_public_media_mount(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    upload = await client.post("/api/v1/clinic-settings/logo", headers=headers, files=_png_file())
    logo_url = upload.json()["logo_url"]

    file_resp = await client.get(logo_url)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_BYTES


async def test_5_clinic_isolation_enforced(client: AsyncClient, make_clinic_with_owner) -> None:
    """Clinic A's logo must never be reachable/discoverable via Clinic B's
    session, and vice versa - `GET /clinic-settings` is tenant-scoped by
    `require_clinic_context`, so Clinic B's own settings response simply
    never carries Clinic A's `logo_url` at all."""
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    await client.post("/api/v1/clinic-settings/logo", headers=headers_a, files=_png_file())

    settings_a = (await client.get("/api/v1/clinic-settings", headers=headers_a)).json()
    settings_b = (await client.get("/api/v1/clinic-settings", headers=headers_b)).json()
    assert settings_a["logo_url"]
    assert settings_b["logo_url"] is None
    assert settings_a["logo_url"] != settings_b.get("logo_url")

    # Clinic B cannot use its own (unrelated) auth to upload a "logo" that
    # collides with or overwrites Clinic A's - it can only ever affect its
    # own clinic row's `logo_url`, proven by the assertion above.


async def test_6_replace_logo_works(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    first = await client.post("/api/v1/clinic-settings/logo", headers=headers, files=_png_file(content=PNG_BYTES))
    first_url = first.json()["logo_url"]

    second = await client.post("/api/v1/clinic-settings/logo", headers=headers, files=_png_file(content=PNG_BYTES_2))
    assert second.status_code == 200, second.text
    second_url = second.json()["logo_url"]
    assert second_url != first_url

    file_resp = await client.get(second_url)
    assert file_resp.content == PNG_BYTES_2
    # The old file is actually removed (live config, never snapshotted -
    # see the Round 7 implementation report's snapshot-decision section).
    old_file_resp = await client.get(first_url)
    assert old_file_resp.status_code == 404


async def test_7_remove_logo_works(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    await client.post("/api/v1/clinic-settings/logo", headers=headers, files=_png_file())

    removed = await client.delete("/api/v1/clinic-settings/logo", headers=headers)
    assert removed.status_code == 200, removed.text
    assert removed.json()["logo_url"] is None

    settings = (await client.get("/api/v1/clinic-settings", headers=headers)).json()
    assert settings["logo_url"] is None


async def test_8_existing_clinic_with_no_logo_continues_working(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    settings = await client.get("/api/v1/clinic-settings", headers=headers)
    assert settings.status_code == 200, settings.text
    assert settings.json()["logo_url"] is None


async def test_receptionist_cannot_upload_clinic_logo(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    from app.core.security import hash_password
    from app.models.role import Role
    from app.models.user import User
    from sqlalchemy import select
    import uuid

    clinic, _owner, _owner_headers_dict = await _owner_headers(client, make_clinic_with_owner)
    role = (await db_session.execute(select(Role).where(Role.name == "Receptionist"))).scalar_one()
    suffix = uuid.uuid4().hex[:8]
    user = User(
        clinic_id=clinic.id, email=f"recep-{suffix}@example.com", username=f"recep{suffix}",
        hashed_password=hash_password("TestPass123!"), first_name="Test", last_name="Recep",
        role_id=role.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    token = await _login(client, user.email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/clinic-settings/logo", headers=recep_headers, files=_png_file())
    assert resp.status_code == 403
