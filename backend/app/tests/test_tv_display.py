"""Integration tests for Phase 13 Live TV Queue Display.

Covers: display-config CRUD (Owner/Administrator-only, other roles 403);
announcement CRUD; the public snapshot endpoint with ZERO Authorization
header, correctly scoped by branch/department/doctor and to
ACTIVE_QUEUE_STATUSES only (no Completed/Cancelled/Skipped entries);
unknown/invalid public_slug -> 404 (not 500, no data leak); tenant
isolation across two clinics' public slugs.
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


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, doctor_id=None, password: str = "TestPass123!"):
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


async def _setup_queue_deps(client: AsyncClient, headers: dict, *, branch_name="Main Branch", branch_code="MAIN") -> dict:
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": branch_name, "code": branch_code})).json()
    department = (
        await client.post("/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General Medicine"})
    ).json()
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Jose", "last_name": "Rizal"})
    ).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": "300.00"},
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


async def test_create_update_delete_display_config_owner_admin_only(client: AsyncClient, make_clinic_with_owner, db_session):
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    create_resp = await client.post(
        "/api/v1/tv-displays", headers=owner_headers,
        json={"branch_id": deps["branch_id"], "display_name": "Lobby TV", "is_public": True, "queue_size": 5},
    )
    assert create_resp.status_code == 201, create_resp.text
    config = create_resp.json()
    assert config["is_public"] is True
    assert config["public_slug"]

    update_resp = await client.patch(
        f"/api/v1/tv-displays/{config['id']}", headers=owner_headers, json={"font_size": "ExtraLarge"}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["font_size"] == "ExtraLarge"

    del_resp = await client.delete(f"/api/v1/tv-displays/{config['id']}", headers=owner_headers)
    assert del_resp.status_code == 204

    # Receptionist has full management access, including delete (front-desk
    # owns operating/maintaining the waiting-room screens); other roles
    # (e.g. Doctor) still get 403 on everything.
    recep_email, _u = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}
    recep_create = await client.post(
        "/api/v1/tv-displays", headers=recep_headers, json={"display_name": "Recep TV", "is_public": False}
    )
    assert recep_create.status_code == 201, recep_create.text

    recep_delete = await client.delete(f"/api/v1/tv-displays/{recep_create.json()['id']}", headers=recep_headers)
    assert recep_delete.status_code == 204

    doctor_email, _u2 = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor")
    doctor_token = await _login(client, doctor_email, "TestPass123!")
    doctor_headers = {"Authorization": f"Bearer {doctor_token}"}
    forbidden = await client.post(
        "/api/v1/tv-displays", headers=doctor_headers, json={"display_name": "X", "is_public": False}
    )
    assert forbidden.status_code == 403


async def test_announcement_create_list_update(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    config = (
        await client.post("/api/v1/tv-displays", headers=owner_headers, json={"display_name": "TV1", "is_public": False})
    ).json()

    ann_resp = await client.post(
        f"/api/v1/tv-displays/{config['id']}/announcements", headers=owner_headers,
        json={"message": "Wash your hands!", "announcement_type": "HealthTip", "display_order": 1},
    )
    assert ann_resp.status_code == 201, ann_resp.text
    announcement = ann_resp.json()
    assert announcement["tv_display_config_id"] == config["id"]

    list_resp = await client.get(f"/api/v1/tv-displays/{config['id']}/announcements", headers=owner_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    update_resp = await client.patch(
        f"/api/v1/announcements/{announcement['id']}", headers=owner_headers, json={"is_active": False}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_active"] is False


async def test_public_endpoint_zero_auth_header_returns_correct_data(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"branch_id": deps["branch_id"], "display_name": "Public TV", "is_public": True},
        )
    ).json()
    slug = config["public_slug"]

    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()

    # ZERO Authorization header - no headers dict passed at all.
    public_resp = await client.get(f"/api/v1/public/tv-display/{slug}")
    assert public_resp.status_code == 200, public_resp.text
    data = public_resp.json()
    assert data["next_waiting"], "expected the freshly created Waiting ticket to appear"
    entry = data["next_waiting"][0]
    assert entry["queue_number"] == queue["queue_number"]
    assert entry["patient_initials"] == "JD"  # Juan Dela Cruz
    assert "Dela Cruz" not in str(data)  # never leaks the full patient name
    assert "Juan" not in str(data)


async def test_public_endpoint_exposes_classification_never_patient_name(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Phase 2.7 (YAKAP Patient Classification): the public TV snapshot may
    expose the queue number and YAKAP/Regular classification, but the
    patient's actual name must never appear anywhere in the response - not
    even once the ticket is Called (Now Serving), which is where the
    classification badge is meant to render."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"branch_id": deps["branch_id"], "display_name": "Public TV", "is_public": True},
        )
    ).json()
    slug = config["public_slug"]

    queue = (
        await client.post(
            "/api/v1/queues", headers=owner_headers, json=_queue_payload(deps, visit_classification="Yakap")
        )
    ).json()
    assert queue["visit_classification"] == "Yakap"

    await client.patch(
        f"/api/v1/queues/{queue['id']}/status", headers=owner_headers, json={"status": "Called"}
    )

    public_resp = await client.get(f"/api/v1/public/tv-display/{slug}")
    assert public_resp.status_code == 200, public_resp.text
    data = public_resp.json()
    assert data["now_serving"], "expected the Called ticket to appear under now_serving"
    entry = data["now_serving"][0]
    assert entry["queue_number"] == queue["queue_number"]
    assert entry["visit_classification"] == "Yakap"
    assert entry["patient_initials"] == "JD"
    assert "Dela Cruz" not in str(data)
    assert "Juan" not in str(data)


async def test_public_endpoint_excludes_completed_queue(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"branch_id": deps["branch_id"], "display_name": "Public TV", "is_public": True},
        )
    ).json()
    slug = config["public_slug"]

    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    await client.post(f"/api/v1/queues/{queue['id']}/cancel", headers=owner_headers)

    resp = await client.get(f"/api/v1/public/tv-display/{slug}")
    assert resp.status_code == 200
    data = resp.json()
    all_numbers = [e["queue_number"] for e in data["next_waiting"]] + [e["queue_number"] for e in data["now_serving"]]
    assert queue["queue_number"] not in all_numbers


async def test_public_endpoint_respects_branch_scoping(client: AsyncClient, make_clinic_with_owner):
    """Uses department scoping (rather than a second branch) to prove the
    scope filter works, sidestepping an unrelated pre-existing bug found
    while writing this test: `VisitCounter` is scoped per (clinic, branch,
    date) but the generated `visit_number` string itself has no branch
    component and is enforced unique only per (clinic, visit_number) - two
    *different* branches' same-day counters both starting at 1 collide on
    "VIS-YYYYMMDD-000001". This is a Phase 6/11 issue, out of scope for
    Phase 13 to fix; flagged in docs/TESTING.md instead. Department-scoped
    filtering exercises the exact same code path (`TvDisplayConfig.
    department_id` filter in `TvDisplayService._build_display_data`) without
    hitting the multi-branch visit-numbering collision."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_queue_deps(client, owner_headers)
    department_b = (
        await client.post("/api/v1/departments", headers=owner_headers, json={"department_code": "PED", "name": "Pediatrics"})
    ).json()
    patient_b = (
        await client.post(
            "/api/v1/patients", headers=owner_headers,
            json={
                "first_name": "Maria", "last_name": "Santos", "birth_date": "1985-03-20",
                "gender": "Female", "civil_status": "Single", "mobile_number": "+639171234599",
            },
        )
    ).json()["patient"]
    deps_b = {**deps_a, "department_id": department_b["id"], "patient_id": patient_b["id"]}

    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"department_id": deps_a["department_id"], "display_name": "Dept A TV", "is_public": True},
        )
    ).json()
    slug = config["public_slug"]

    queue_a = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps_a))).json()
    queue_b = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps_b))).json()

    resp = await client.get(f"/api/v1/public/tv-display/{slug}")
    assert resp.status_code == 200
    ids = [e["queue_id"] for e in resp.json()["next_waiting"]]
    assert queue_a["id"] in ids
    assert queue_b["id"] not in ids


async def test_unknown_public_slug_returns_404(client: AsyncClient):
    resp = await client.get("/api/v1/public/tv-display/not-a-real-slug")
    assert resp.status_code == 404


async def test_tenant_isolation_public_slug_never_leaks_across_clinics(client: AsyncClient, make_clinic_with_owner):
    clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_queue_deps(client, headers_a)
    config_a = (
        await client.post(
            "/api/v1/tv-displays", headers=headers_a,
            json={"branch_id": deps_a["branch_id"], "display_name": "Clinic A TV", "is_public": True},
        )
    ).json()
    queue_a = (await client.post("/api/v1/queues", headers=headers_a, json=_queue_payload(deps_a))).json()

    clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    deps_b = await _setup_queue_deps(client, headers_b, branch_name="B Branch", branch_code="BB")
    config_b = (
        await client.post(
            "/api/v1/tv-displays", headers=headers_b,
            json={"branch_id": deps_b["branch_id"], "display_name": "Clinic B TV", "is_public": True},
        )
    ).json()
    queue_b = (await client.post("/api/v1/queues", headers=headers_b, json=_queue_payload(deps_b))).json()

    resp_a = await client.get(f"/api/v1/public/tv-display/{config_a['public_slug']}")
    ids_a = [e["queue_id"] for e in resp_a.json()["next_waiting"]]
    assert queue_a["id"] in ids_a
    assert queue_b["id"] not in ids_a

    resp_b = await client.get(f"/api/v1/public/tv-display/{config_b['public_slug']}")
    ids_b = [e["queue_id"] for e in resp_b.json()["next_waiting"]]
    assert queue_b["id"] in ids_b
    assert queue_a["id"] not in ids_b

    # Clinic B's owner cannot fetch clinic A's config by id either.
    cross = await client.get(f"/api/v1/tv-displays/{config_a['id']}", headers=headers_b)
    assert cross.status_code == 404


# ---- Post-RC1: 50/50 Information/Advertisement Panel ----------------------


async def test_info_content_create_list_update_delete_owner_admin_only(
    client: AsyncClient, make_clinic_with_owner, db_session
):
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)

    create_resp = await client.post(
        "/api/v1/tv-info-content", headers=owner_headers,
        json={"title": "Flu Shots Available", "body": "Ask our staff about seasonal flu vaccination.", "content_type": "Promotion", "duration_seconds": 8, "display_order": 1},
    )
    assert create_resp.status_code == 201, create_resp.text
    content = create_resp.json()
    assert content["title"] == "Flu Shots Available"
    assert content["duration_seconds"] == 8
    assert content["is_active"] is True

    list_resp = await client.get("/api/v1/tv-info-content", headers=owner_headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    update_resp = await client.patch(
        f"/api/v1/tv-info-content/{content['id']}", headers=owner_headers, json={"is_active": False}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["is_active"] is False

    del_resp = await client.delete(f"/api/v1/tv-info-content/{content['id']}", headers=owner_headers)
    assert del_resp.status_code == 204
    list_after = await client.get("/api/v1/tv-info-content", headers=owner_headers)
    assert list_after.json() == []

    # Receptionist has full management access, including delete; other
    # roles (e.g. Doctor) get 403.
    recep_email, _u = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}
    recep_create = await client.post(
        "/api/v1/tv-info-content", headers=recep_headers, json={"title": "Recep Content", "body": "Y"}
    )
    assert recep_create.status_code == 201, recep_create.text

    recep_delete = await client.delete(f"/api/v1/tv-info-content/{recep_create.json()['id']}", headers=recep_headers)
    assert recep_delete.status_code == 204

    doctor_email, _u2 = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor")
    doctor_token = await _login(client, doctor_email, "TestPass123!")
    doctor_headers = {"Authorization": f"Bearer {doctor_token}"}
    forbidden = await client.post(
        "/api/v1/tv-info-content", headers=doctor_headers, json={"title": "X", "body": "Y"}
    )
    assert forbidden.status_code == 403
    # But viewer-tier roles can still read.
    readable = await client.get("/api/v1/tv-info-content", headers=doctor_headers)
    assert readable.status_code == 200


async def test_public_display_data_includes_only_active_info_content_ordered(
    client: AsyncClient, make_clinic_with_owner
):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"branch_id": deps["branch_id"], "display_name": "Info Panel TV", "is_public": True},
        )
    ).json()
    slug = config["public_slug"]

    await client.post(
        "/api/v1/tv-info-content", headers=owner_headers,
        json={"title": "Second", "body": "b", "display_order": 2},
    )
    await client.post(
        "/api/v1/tv-info-content", headers=owner_headers,
        json={"title": "First", "body": "a", "display_order": 1},
    )
    inactive = (
        await client.post(
            "/api/v1/tv-info-content", headers=owner_headers,
            json={"title": "Hidden", "body": "c", "display_order": 0, "is_active": False},
        )
    ).json()
    assert inactive["is_active"] is False

    resp = await client.get(f"/api/v1/public/tv-display/{slug}")
    assert resp.status_code == 200
    titles = [c["title"] for c in resp.json()["info_content"]]
    assert titles == ["First", "Second"]


async def test_public_display_data_empty_info_panel_when_no_active_content(
    client: AsyncClient, make_clinic_with_owner
):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"branch_id": deps["branch_id"], "display_name": "Empty Info TV", "is_public": True},
        )
    ).json()
    resp = await client.get(f"/api/v1/public/tv-display/{config['public_slug']}")
    assert resp.status_code == 200
    assert resp.json()["info_content"] == []


async def test_info_content_image_upload_validation_and_delete(
    client: AsyncClient, make_clinic_with_owner, db_session
):
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    content = (
        await client.post(
            "/api/v1/tv-info-content", headers=owner_headers,
            json={"title": "Annual Check-up Package", "body": "Bundled rate this month."},
        )
    ).json()
    assert content["image_url"] is None

    # Disallowed extension is rejected before anything is written.
    bad_ext = await client.post(
        f"/api/v1/tv-info-content/{content['id']}/image", headers=owner_headers,
        files={"file": ("malware.exe", b"not-an-image", "application/octet-stream")},
    )
    assert bad_ext.status_code == 400

    # A real (tiny, valid) PNG upload succeeds and sets image_url to a
    # locally-served path.
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
        "53de0000000c4944415478da6360000002000155a8f3580000000049454e44ae426082"
    )
    upload = await client.post(
        f"/api/v1/tv-info-content/{content['id']}/image", headers=owner_headers,
        files={"file": ("photo.png", png_bytes, "image/png")},
    )
    assert upload.status_code == 200, upload.text
    updated = upload.json()
    assert updated["image_url"] is not None
    assert updated["image_url"].startswith("/media/tv-info-content/")

    # The uploaded file is actually retrievable via the static mount, with
    # zero auth (same security model as the public TV display itself).
    fetched = await client.get(updated["image_url"])
    assert fetched.status_code == 200
    assert fetched.content == png_bytes

    # Removing the photo clears image_url and the file 404s afterward.
    removed = await client.delete(f"/api/v1/tv-info-content/{content['id']}/image", headers=owner_headers)
    assert removed.status_code == 200
    assert removed.json()["image_url"] is None
    gone = await client.get(updated["image_url"])
    assert gone.status_code == 404

    # Receptionist can also upload and delete the image; other roles (e.g.
    # Doctor) get 403.
    recep_email, _u = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}
    recep_upload = await client.post(
        f"/api/v1/tv-info-content/{content['id']}/image", headers=recep_headers,
        files={"file": ("photo2.png", png_bytes, "image/png")},
    )
    assert recep_upload.status_code == 200, recep_upload.text

    recep_delete_image = await client.delete(f"/api/v1/tv-info-content/{content['id']}/image", headers=recep_headers)
    assert recep_delete_image.status_code == 200
    assert recep_delete_image.json()["image_url"] is None

    doctor_email, _u2 = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor")
    doctor_token = await _login(client, doctor_email, "TestPass123!")
    doctor_headers = {"Authorization": f"Bearer {doctor_token}"}
    forbidden = await client.post(
        f"/api/v1/tv-info-content/{content['id']}/image", headers=doctor_headers,
        files={"file": ("photo.png", png_bytes, "image/png")},
    )
    assert forbidden.status_code == 403


# ---- Post-RC1: short TV display URL (short_code alias) --------------------


async def test_short_code_set_at_creation_and_resolves_the_same_display(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    code = f"canora-{uuid.uuid4().hex[:8]}"
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"display_name": "Lobby TV", "is_public": True, "short_code": code},
        )
    ).json()
    assert config["short_code"] == code
    assert config["public_slug"]

    # Both the long public_slug and the short short_code resolve the exact
    # same display - same clinic/branch/theme etc, not just "some" 200.
    by_slug = await client.get(f"/api/v1/public/tv-display/{config['public_slug']}")
    by_code = await client.get(f"/api/v1/public/tv-display/{code}")
    assert by_slug.status_code == 200
    assert by_code.status_code == 200
    assert by_slug.json()["display_name"] == by_code.json()["display_name"] == "Lobby TV"
    # The short-code response still carries the REAL public_slug as
    # ws_auth_slug - the WebSocket auth path never accepts the short code
    # itself, only ever the true high-entropy slug (see
    # `use-tv-display-realtime.ts::resolveWsToken` on the frontend side).
    assert by_code.json()["ws_auth_slug"] == config["public_slug"]


async def test_short_code_is_case_insensitive(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    code = f"canora-{uuid.uuid4().hex[:8]}"
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"display_name": "Lobby TV", "is_public": True, "short_code": code.upper()},
        )
    ).json()
    # Normalized to lowercase server-side.
    assert config["short_code"] == code

    resp = await client.get(f"/api/v1/public/tv-display/{code}")
    assert resp.status_code == 200


async def test_short_code_uniqueness_enforced_across_displays(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    code = f"canora-{uuid.uuid4().hex[:8]}"
    other_code = f"other-{uuid.uuid4().hex[:8]}"
    await client.post(
        "/api/v1/tv-displays", headers=owner_headers,
        json={"display_name": "Lobby TV", "is_public": True, "short_code": code},
    )
    dupe = await client.post(
        "/api/v1/tv-displays", headers=owner_headers,
        json={"display_name": "Second TV", "is_public": True, "short_code": code},
    )
    assert dupe.status_code == 409

    # Also enforced on update.
    second = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"display_name": "Second TV", "is_public": True, "short_code": other_code},
        )
    ).json()
    update_dupe = await client.patch(
        f"/api/v1/tv-displays/{second['id']}", headers=owner_headers, json={"short_code": code}
    )
    assert update_dupe.status_code == 409

    # Re-saving a display's own current code is not a conflict.
    noop_update = await client.patch(
        f"/api/v1/tv-displays/{second['id']}", headers=owner_headers, json={"short_code": other_code}
    )
    assert noop_update.status_code == 200


async def test_unknown_short_code_returns_404_not_leaked_data(client: AsyncClient):
    resp = await client.get("/api/v1/public/tv-display/no-such-code")
    assert resp.status_code == 404


async def test_short_code_respects_is_public_and_is_active_like_public_slug(
    client: AsyncClient, make_clinic_with_owner
):
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    code = f"canora-{uuid.uuid4().hex[:8]}"
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"display_name": "Lobby TV", "is_public": True, "short_code": code},
        )
    ).json()
    resp = await client.get(f"/api/v1/public/tv-display/{code}")
    assert resp.status_code == 200

    # Disabling the display (is_active=false) stops the short code from
    # resolving too - same access-control filters as public_slug, not a
    # separate/weaker gate.
    await client.patch(f"/api/v1/tv-displays/{config['id']}", headers=owner_headers, json={"is_active": False})
    resp_after = await client.get(f"/api/v1/public/tv-display/{code}")
    assert resp_after.status_code == 404


async def test_long_public_slug_url_still_works_after_short_code_feature_added(
    client: AsyncClient, make_clinic_with_owner
):
    """Backward-compat: a display with no short_code at all still resolves
    via its long public_slug exactly as before this feature."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers, json={"display_name": "No Code TV", "is_public": True}
        )
    ).json()
    assert config["short_code"] is None
    resp = await client.get(f"/api/v1/public/tv-display/{config['public_slug']}")
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "No Code TV"


async def test_released_laboratory_result_removes_ticket_from_now_serving(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Bug fix regression: a queue ticket Called for a Laboratory-only
    encounter (never Serving) previously stayed on the TV display's "Now
    Serving" list forever once the lab work finished, because nothing ever
    moved `Queue.status` off Called. This goes through the REAL laboratory
    release endpoint (not a direct DB/queue-status write) and asserts the
    ticket disappears from the public TV snapshot - proving the underlying
    Queue state changed (it's excluded via the existing
    `ACTIVE_QUEUE_STATUSES` filter every other ticket already uses), not
    that a Laboratory-specific filter was bolted onto the TV display
    itself."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    config = (
        await client.post(
            "/api/v1/tv-displays", headers=owner_headers,
            json={"branch_id": deps["branch_id"], "display_name": "Public TV", "is_public": True},
        )
    ).json()
    slug = config["public_slug"]

    await client.post(
        "/api/v1/laboratory/templates", headers=owner_headers,
        json={"test_name": "CBC", "default_price": "0", "parameters": []},
    )
    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token_resp = await client.post("/api/v1/auth/login", json={"email_or_username": doc_email, "password": "TestPass123!"})
    doc_headers = {"Authorization": f"Bearer {doc_token_resp.json()['access_token']}"}

    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)

    # Confirm the ticket IS on Now Serving before release - proves this test
    # actually exercises the bug's visible symptom, not just backend state.
    before = (await client.get(f"/api/v1/public/tv-display/{slug}")).json()
    assert any(e["queue_number"] == queue["queue_number"] for e in before["now_serving"]), (
        "expected the Called laboratory ticket to appear under now_serving before release"
    )

    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    order = (
        await client.post(
            f"/api/v1/consultations/{opened['id']}/orders", headers=doc_headers,
            json={"order_category": "Laboratory", "items": [{"item_name": "CBC"}]},
        )
    ).json()
    lab_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={visit_id}", headers=owner_headers)).json()
    lab_id = next(lo for lo in lab_orders if lo["order_id"] == order["id"])["id"]

    lab_email, _lab_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_token_resp = await client.post("/api/v1/auth/login", json={"email_or_username": lab_email, "password": "TestPass123!"})
    lab_headers = {"Authorization": f"Bearer {lab_token_resp.json()['access_token']}"}

    await client.post(f"/api/v1/laboratory/orders/{lab_id}/collect", headers=lab_headers)
    await client.post(f"/api/v1/laboratory/orders/{lab_id}/start-processing", headers=lab_headers)
    await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/results", headers=lab_headers,
        json={"results": [{"parameter_name": "Note", "result_type": "Text", "text_value": "ok"}]},
    )
    # Pathologist selection is now MANDATORY at release (product decision).
    pathologist_resp = await client.post(
        "/api/v1/pathologists",
        headers=owner_headers, json={"name": "Dr. Maria Santos", "license_number": "PRC-12345"},
    )
    assert pathologist_resp.status_code == 201, pathologist_resp.text
    released = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release",
        headers=lab_headers, json={"pathologist_id": pathologist_resp.json()["id"]},
    )
    assert released.status_code == 200, released.text

    after = (await client.get(f"/api/v1/public/tv-display/{slug}")).json()
    assert not any(e["queue_number"] == queue["queue_number"] for e in after["now_serving"]), (
        "released laboratory ticket must no longer appear under now_serving"
    )
    assert not any(e["queue_number"] == queue["queue_number"] for e in after["next_waiting"])
