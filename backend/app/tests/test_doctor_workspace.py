"""Integration tests for Phase 7 Doctor Workspace: dashboard stats, doctor-
scoped queue (with Administrator all/filter-by-doctor), call/start/complete
consultation lifecycle (Visit status + timeline + doctor_activity + audit),
waiting-time/consultation-duration computation, visit locking (acquire,
second-user blocked, release/expiry takeover), recall, no-show/cancel,
tenant isolation, and role gating.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.role import Role

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """This test module logs in several distinct users per test (owner +
    multiple doctors/receptionist), which can exceed the in-memory login
    rate limiter's fixed window (`RATE_LIMIT_LOGIN_MAX_ATTEMPTS` per
    `RATE_LIMIT_LOGIN_WINDOW_SECONDS`, shared process-global state - see
    `app/core/rate_limit.py`) across a fast-running test file. Reset the
    in-memory bucket before each test so this module's login volume doesn't
    trip a limiter meant to catch brute-force attempts, not legitimate
    multi-user test setup."""
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


async def _make_doctor_login(
    db_session: AsyncSession, *, clinic_id, doctor_id, password: str = "DoctorPass123!"
) -> tuple[str, dict]:
    """Creates a User with the Doctor role linked to `doctor_id` and returns (email, headers-less)."""
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


async def test_dashboard_stats_compute_correctly(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    await _create_visit(client, owner_headers, deps)

    doc_email, _doc_user = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    resp = await client.get("/api/v1/doctor-workspace/dashboard", headers=doc_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["stats"]["waiting"] == 1
    assert body["stats"]["called"] == 0
    assert body["doctor_name"] == "Jose Rizal"


async def test_doctor_queue_scoped_to_own_visits_admin_sees_all(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    await _create_visit(client, owner_headers, deps)

    # A second doctor with no visits assigned.
    doctor2 = (await client.post("/api/v1/doctors", headers=owner_headers, json={"first_name": "Ana", "last_name": "Lopez"})).json()
    doc_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc2_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=doctor2["id"])

    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc2_token = await _login(client, doc2_email, "DoctorPass123!")

    r1 = await client.get("/api/v1/doctor-workspace/queue", headers={"Authorization": f"Bearer {doc_token}"})
    assert r1.json()["total"] == 1

    r2 = await client.get("/api/v1/doctor-workspace/queue", headers={"Authorization": f"Bearer {doc2_token}"})
    assert r2.json()["total"] == 0

    # Owner/Administrator sees all (no doctor_id filter).
    r3 = await client.get("/api/v1/doctor-workspace/queue", headers=owner_headers)
    assert r3.json()["total"] == 1

    # Owner filtered by doctor_id explicitly.
    r4 = await client.get(
        "/api/v1/doctor-workspace/queue", headers=owner_headers, params={"doctor_id": deps["doctor_id"]}
    )
    assert r4.json()["total"] == 1


async def test_call_start_complete_lifecycle(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    call_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    assert call_resp.status_code == 200, call_resp.text
    assert call_resp.json()["status"] == "Called"
    assert "Called" in [t["event_type"] for t in call_resp.json()["timeline"]]

    start_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    assert start_resp.status_code == 200, start_resp.text
    assert start_resp.json()["status"] == "InConsultation"
    assert start_resp.json()["consultation_start"] is not None

    complete_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/complete-consultation", headers=doc_headers)
    assert complete_resp.status_code == 200, complete_resp.text
    assert complete_resp.json()["status"] == "Completed"

    # doctor_activity rows were written at each step.
    from app.models.doctor_activity import DoctorActivity

    rows = (await db_session.execute(select(DoctorActivity).where(DoctorActivity.visit_id == uuid.UUID(visit_id)))).scalars().all()
    activity_types = {r.activity_type.value for r in rows}
    assert {"PatientCalled", "ConsultationStarted", "ConsultationCompleted"} <= activity_types

    # audit_logs entries were written too.
    from app.models.audit_log import AuditLog

    audit_rows = (
        await db_session.execute(select(AuditLog).where(AuditLog.entity_id == visit_id, AuditLog.action.like("doctor_workspace.%")))
    ).scalars().all()
    assert len(audit_rows) >= 3

    # consultation_sessions row closed with a duration.
    from app.models.consultation_session import ConsultationSession

    sessions = (await db_session.execute(select(ConsultationSession).where(ConsultationSession.visit_id == uuid.UUID(visit_id)))).scalars().all()
    assert len(sessions) == 1
    assert sessions[0].status.value == "Ended"
    assert sessions[0].duration_seconds is not None

    # Dashboard now reflects a real average consultation duration.
    dash = await client.get("/api/v1/doctor-workspace/dashboard", headers=doc_headers)
    assert dash.json()["stats"]["completed_today"] == 1
    assert dash.json()["stats"]["avg_consultation_seconds"] is not None


async def test_waiting_time_computed(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    await _create_visit(client, owner_headers, deps)

    doc_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    resp = await client.get("/api/v1/doctor-workspace/queue", headers={"Authorization": f"Bearer {doc_token}"})
    item = resp.json()["items"][0]
    assert item["status"] == "Waiting"
    assert item["waiting_seconds"] is not None
    assert item["waiting_seconds"] >= 0


async def test_recall_rebroadcasts_without_status_change(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    recall_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/recall", headers=doc_headers)
    assert recall_resp.status_code == 200, recall_resp.text
    assert recall_resp.json()["status"] == "Called"

    # Recalling a visit that isn't Called should fail.
    other_queue = await _create_visit(
        client, owner_headers,
        {**deps, "patient_id": (await client.post(
            "/api/v1/patients", headers=owner_headers,
            json={"first_name": "Second", "last_name": "P", "birth_date": "1991-01-01", "gender": "Female",
                  "civil_status": "Single", "mobile_number": "+639171234599"},
        )).json()["patient"]["id"]},
    )
    bad_recall = await client.post(f"/api/v1/doctor-workspace/visits/{other_queue['visit_id']}/recall", headers=doc_headers)
    assert bad_recall.status_code == 400


async def test_no_show_and_cancel(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    no_show = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/no-show", headers=doc_headers)
    assert no_show.status_code == 200, no_show.text
    assert no_show.json()["status"] == "NoShow"

    # Second visit, cancel path.
    patient2 = (await client.post(
        "/api/v1/patients", headers=owner_headers,
        json={"first_name": "Third", "last_name": "P", "birth_date": "1991-01-01", "gender": "Female",
              "civil_status": "Single", "mobile_number": "+639171234598"},
    )).json()["patient"]
    queue2 = await _create_visit(client, owner_headers, {**deps, "patient_id": patient2["id"]})
    cancel = await client.post(
        f"/api/v1/doctor-workspace/visits/{queue2['visit_id']}/cancel", headers=doc_headers, json={"reason": "Patient left"}
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "Cancelled"


async def test_visit_locking_second_user_blocked_then_released(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    open_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/open", headers=doc_headers)
    assert open_resp.status_code == 200
    assert open_resp.json()["locked"] is True
    assert open_resp.json()["is_self"] is True

    # Owner (privileged) opening the same visit gets lock-holder info, not edit access.
    other_open = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/open", headers=owner_headers)
    assert other_open.status_code == 200
    body = other_open.json()
    assert body["locked"] is True
    assert body["is_self"] is False
    assert body["locked_by_name"] == "Test Doctor"

    # Release the lock explicitly, then the second caller can acquire it.
    release_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/release-lock", headers=doc_headers)
    assert release_resp.status_code == 200
    assert release_resp.json()["locked"] is False

    reacquire = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/open", headers=owner_headers)
    assert reacquire.status_code == 200
    assert reacquire.json()["is_self"] is True


async def test_visit_lock_expires_and_allows_takeover(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    from app.models.visit_lock import VisitLock

    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    doc_email, doc_user = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/open", headers=doc_headers)

    # Backdate the lock to simulate a stale (expired) heartbeat.
    lock = (
        await db_session.execute(
            select(VisitLock).where(VisitLock.visit_id == uuid.UUID(visit_id), VisitLock.released_at.is_(None))
        )
    ).scalars().first()
    lock.locked_at = datetime.now(UTC) - timedelta(minutes=30)
    await db_session.commit()

    takeover = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/open", headers=owner_headers)
    assert takeover.status_code == 200
    assert takeover.json()["is_self"] is True


async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_queue_deps(client, headers_a)
    queue_a = await _create_visit(client, headers_a, deps_a)

    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    resp = await client.post(f"/api/v1/doctor-workspace/visits/{queue_a['visit_id']}/call", headers=headers_b)
    assert resp.status_code == 404


async def test_role_gating_receptionist_read_only_doctor_scoped(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = await _create_visit(client, owner_headers, deps)
    visit_id = queue["visit_id"]

    rec_email, _ = await _make_receptionist_login(db_session, clinic_id=clinic.id)
    rec_token = await _login(client, rec_email, "ReceptPass123!")
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    # Receptionist can view.
    view_resp = await client.get("/api/v1/doctor-workspace/queue", headers=rec_headers)
    assert view_resp.status_code == 200

    # Receptionist cannot act.
    call_resp = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=rec_headers)
    assert call_resp.status_code == 403

    # A doctor not assigned to this visit cannot act on it either.
    doctor2 = (await client.post("/api/v1/doctors", headers=owner_headers, json={"first_name": "Ana", "last_name": "Lopez"})).json()
    doc2_email, _ = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=doctor2["id"])
    doc2_token = await _login(client, doc2_email, "DoctorPass123!")
    unauthorized = await client.post(
        f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers={"Authorization": f"Bearer {doc2_token}"}
    )
    assert unauthorized.status_code == 403
