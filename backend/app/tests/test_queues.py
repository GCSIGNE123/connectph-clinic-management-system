"""Integration tests for Phase 5 Reception & Queue Management: create,
number generation (sequential/daily-reset/concurrency-safe), duplicate-active
rejection, inactive doctor/department/service rejection, archived-patient
rejection, status transitions + history, list/search/filter, tenant isolation.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.dependencies import get_db
from app.main import app

pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, clinic_slug: str, email: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email_or_username": email, "password": password, "clinic_slug": clinic_slug},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    token = await _login(client, clinic.slug, owner.email, password)
    return clinic, owner, {"Authorization": f"Bearer {token}"}


async def _setup_queue_deps(client: AsyncClient, headers: dict) -> dict:
    """Create a branch/department/doctor/service/patient needed to raise a queue ticket."""
    branch = (
        await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})
    ).json()
    department = (
        await client.post(
            "/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General Medicine"}
        )
    ).json()
    doctor = (
        await client.post(
            "/api/v1/doctors", headers=headers, json={"first_name": "Jose", "last_name": "Rizal"}
        )
    ).json()
    service = (
        await client.post(
            "/api/v1/services",
            headers=headers,
            json={"service_code": "MEDCERT", "service_name": "Medical Certificate", "default_price": "500.00"},
        )
    ).json()
    patient = (
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Juan",
                "last_name": "Dela Cruz",
                "birth_date": "1990-05-15",
                "gender": "Male",
                "civil_status": "Single",
                "mobile_number": "+639171234567",
            },
        )
    ).json()["patient"]
    return {
        "branch_id": branch["id"],
        "department_id": department["id"],
        "doctor_id": doctor["id"],
        "service_id": service["id"],
        "patient_id": patient["id"],
    }


def _queue_payload(deps: dict, **overrides) -> dict:
    payload = {
        "patient_id": deps["patient_id"],
        "branch_id": deps["branch_id"],
        "department_id": deps["department_id"],
        "doctor_id": deps["doctor_id"],
        "service_id": deps["service_id"],
        "priority": "Normal",
    }
    payload.update(overrides)
    return payload


async def test_create_queue_generates_sequential_number(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    r1 = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert r1.status_code == 201, r1.text
    q1 = r1.json()
    assert q1["queue_number"] == "A001"
    assert q1["status"] == "Waiting"

    # A second patient (different patient, same department) gets the next number.
    patient2 = (
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Maria",
                "last_name": "Clara",
                "birth_date": "1992-01-01",
                "gender": "Female",
                "civil_status": "Single",
                "mobile_number": "+639171234568",
            },
        )
    ).json()["patient"]
    r2 = await client.post(
        "/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=patient2["id"])
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["queue_number"] == "A002"


async def test_duplicate_active_queue_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    first = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert first.status_code == 201

    dup = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert dup.status_code == 409
    assert "already has an active queue" in dup.json()["detail"]


async def test_inactive_doctor_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    from uuid import UUID

    from app.models.doctor import Doctor, DoctorStatus

    doctor = await db_session.get(Doctor, UUID(deps["doctor_id"]))
    doctor.status = DoctorStatus.INACTIVE
    await db_session.commit()

    response = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert response.status_code == 400
    assert "not active" in response.json()["detail"]


async def test_inactive_department_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    from uuid import UUID

    from app.models.department import Department

    department = await db_session.get(Department, UUID(deps["department_id"]))
    department.status = "Inactive"
    await db_session.commit()

    response = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert response.status_code == 400
    assert "not active" in response.json()["detail"]


async def test_inactive_service_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    from uuid import UUID

    from app.models.clinic_service import ClinicService

    service = await db_session.get(ClinicService, UUID(deps["service_id"]))
    service.status = "Inactive"
    await db_session.commit()

    response = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert response.status_code == 400
    assert "not active" in response.json()["detail"]


async def test_archived_patient_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    archive_response = await client.post(f"/api/v1/patients/{deps['patient_id']}/archive", headers=headers)
    assert archive_response.status_code == 200

    response = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert response.status_code == 400
    assert "archived patient" in response.json()["detail"]


async def test_status_transitions_write_history(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    queue_id = created["id"]

    called = await client.patch(
        f"/api/v1/queues/{queue_id}/status", headers=headers, json={"status": "Called"}
    )
    assert called.status_code == 200, called.text
    assert called.json()["status"] == "Called"

    serving = await client.patch(
        f"/api/v1/queues/{queue_id}/status", headers=headers, json={"status": "Serving"}
    )
    assert serving.status_code == 200
    assert serving.json()["serving_started_at"] is not None

    completed = await client.patch(
        f"/api/v1/queues/{queue_id}/status", headers=headers, json={"status": "Completed"}
    )
    assert completed.status_code == 200
    detail = completed.json()
    assert detail["status"] == "Completed"
    assert detail["completed_at"] is not None
    history = detail["history"]
    assert [h["to_status"] for h in history] == ["Waiting", "Called", "Serving", "Completed"]

    # Terminal state: no further transitions allowed.
    invalid = await client.patch(
        f"/api/v1/queues/{queue_id}/status", headers=headers, json={"status": "Called"}
    )
    assert invalid.status_code == 400


async def test_cancel_queue(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    response = await client.post(f"/api/v1/queues/{created['id']}/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "Cancelled"


async def test_list_and_filter_queues(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))

    response = await client.get(
        "/api/v1/queues", headers=headers, params={"department_id": deps["department_id"], "status": "Waiting"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["queue_number"] == "A001"


async def test_queue_slip_payload(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    response = await client.get(f"/api/v1/queues/{created['id']}/slip", headers=headers)
    assert response.status_code == 200
    slip = response.json()
    assert slip["queue_number"] == "A001"
    assert slip["patient_name"]
    assert slip["qr_token"]


async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_queue_deps(client, headers_a)
    created = (await client.post("/api/v1/queues", headers=headers_a, json=_queue_payload(deps_a))).json()

    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    response = await client.get(f"/api/v1/queues/{created['id']}", headers=headers_b)
    assert response.status_code == 404


async def _make_real_clinic_and_branches(db_session: AsyncSession, count: int = 1):
    """Creates a real Clinic + `count` Branch rows via the ORM directly (no
    HTTP round trip needed) - `queue_counters` has FK constraints to both
    tables, so unit-level generator tests still need real parent rows."""
    import uuid

    from app.models.branch import Branch
    from app.models.clinic import Clinic

    clinic = Clinic(name=f"Gen Test Clinic {uuid.uuid4().hex[:8]}", slug=f"gen-test-{uuid.uuid4().hex[:10]}")
    db_session.add(clinic)
    await db_session.flush()

    branches = []
    for _ in range(count):
        branch = Branch(clinic_id=clinic.id, name=f"Branch {uuid.uuid4().hex[:6]}")
        db_session.add(branch)
        branches.append(branch)
    await db_session.flush()
    await db_session.commit()
    return clinic, branches


async def test_queue_number_generation_resets_daily_and_scoped_by_branch(db_session: AsyncSession) -> None:
    """Direct unit test of QueueNumberGenerator: sequential within a bucket,
    independent across dates and branches."""
    from datetime import date

    from app.services.queue_number_generator import QueueNumberGenerator

    clinic, branches = await _make_real_clinic_and_branches(db_session, count=2)
    branch, branch_2 = branches
    clinic_id = clinic.id
    branch_id = branch.id
    branch_id_2 = branch_2.id

    gen = QueueNumberGenerator(db_session)
    n1 = await gen.next_number(clinic_id, branch_id, "A", date(2026, 7, 26))
    n2 = await gen.next_number(clinic_id, branch_id, "A", date(2026, 7, 26))
    assert n1 == "A001"
    assert n2 == "A002"

    # Different date -> resets.
    n3 = await gen.next_number(clinic_id, branch_id, "A", date(2026, 7, 27))
    assert n3 == "A001"

    # Different branch, same date -> independent counter.
    n4 = await gen.next_number(clinic_id, branch_id_2, "A", date(2026, 7, 26))
    assert n4 == "A001"

    await db_session.rollback()


async def test_queue_number_generation_concurrency_safe(engine, db_session: AsyncSession) -> None:
    """Real concurrency test: fire N concurrent number-generation requests at
    the same (clinic, branch, prefix, date) bucket, each in its own
    transaction/session, and assert every issued number is unique with no gaps."""
    from datetime import date

    from app.services.queue_number_generator import QueueNumberGenerator

    clinic, branches = await _make_real_clinic_and_branches(db_session, count=1)
    clinic_id = clinic.id
    branch_id = branches[0].id
    today = date(2026, 7, 26)

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def _issue_one() -> str:
        async with session_maker() as session:
            number = await QueueNumberGenerator(session).next_number(clinic_id, branch_id, "A", today)
            await session.commit()
            return number

    results = await asyncio.gather(*(_issue_one() for _ in range(20)))
    assert len(results) == len(set(results)) == 20
    assert sorted(results) == [f"A{str(i).zfill(3)}" for i in range(1, 21)]
