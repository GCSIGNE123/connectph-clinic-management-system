"""Integration tests for Phase 6 Visit (Encounter) Management: automatic
visit creation from queue creation, visit number generation (sequential /
daily-reset / clinic+branch-scoped / concurrency-safe), status transitions
writing timeline events, search/filter/pagination, patient visit history,
and tenant isolation.
"""

import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


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
    branch = (
        await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})
    ).json()
    department = (
        await client.post(
            "/api/v1/departments", headers=headers, json={"department_code": "GEN", "name": "General Medicine"}
        )
    ).json()
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Jose", "last_name": "Rizal"})
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


async def _make_patient(client: AsyncClient, headers: dict, *, first_name: str, mobile: str) -> dict:
    return (
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": first_name,
                "last_name": "Clara",
                "birth_date": "1992-01-01",
                "gender": "Female",
                "civil_status": "Single",
                "mobile_number": mobile,
            },
        )
    ).json()["patient"]


async def test_queue_creation_auto_creates_linked_visit(client: AsyncClient, make_clinic_with_owner) -> None:
    """Creating a queue via POST /queues must transactionally create a Visit
    with matching fields and set queue.visit_id (and visit.queue_id)."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    response = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert response.status_code == 201, response.text
    queue = response.json()

    assert queue["visit_id"] is not None
    assert queue["visit_number"] and queue["visit_number"].startswith("VIS-")

    visit_response = await client.get(f"/api/v1/visits/{queue['visit_id']}", headers=headers)
    assert visit_response.status_code == 200, visit_response.text
    visit = visit_response.json()

    assert visit["queue_id"] == queue["id"]
    assert visit["patient_id"] == deps["patient_id"]
    assert visit["doctor_id"] == deps["doctor_id"]
    assert visit["department_id"] == deps["department_id"]
    assert visit["service_id"] == deps["service_id"]
    assert visit["branch_id"] == deps["branch_id"]
    assert visit["status"] == "Waiting"
    assert visit["visit_type"] == "WalkIn"
    assert visit["priority"] == "Normal"
    assert visit["check_in_time"] is not None

    event_types = [t["event_type"] for t in visit["timeline"]]
    assert "Registered" in event_types
    assert "Queued" in event_types


async def test_visit_number_format_sequential(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    r1 = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))
    assert r1.status_code == 201, r1.text
    v1_number = r1.json()["visit_number"]

    patient2 = await _make_patient(client, headers, first_name="Maria", mobile="+639171234568")
    r2 = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=patient2["id"]))
    assert r2.status_code == 201, r2.text
    v2_number = r2.json()["visit_number"]

    import re

    today = __import__("datetime").datetime.now(__import__("datetime").UTC).strftime("%Y%m%d")
    assert re.fullmatch(rf"VIS-{today}-\d{{6}}", v1_number)
    assert re.fullmatch(rf"VIS-{today}-\d{{6}}", v2_number)
    n1 = int(v1_number.rsplit("-", 1)[-1])
    n2 = int(v2_number.rsplit("-", 1)[-1])
    assert n2 == n1 + 1


async def _make_real_clinic_and_branches(db_session: AsyncSession, count: int = 1):
    import uuid

    from app.models.branch import Branch
    from app.models.clinic import Clinic

    clinic = Clinic(name=f"Visit Gen Test Clinic {uuid.uuid4().hex[:8]}", slug=f"visit-gen-test-{uuid.uuid4().hex[:10]}")
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


async def test_visit_number_generation_resets_daily_and_scoped_by_branch(db_session: AsyncSession) -> None:
    from datetime import date

    from app.services.visit_number_generator import VisitNumberGenerator

    clinic, branches = await _make_real_clinic_and_branches(db_session, count=2)
    branch, branch_2 = branches
    clinic_id = clinic.id
    branch_id = branch.id
    branch_id_2 = branch_2.id

    gen = VisitNumberGenerator(db_session)
    n1 = await gen.next_number(clinic_id, branch_id, date(2026, 7, 26))
    n2 = await gen.next_number(clinic_id, branch_id, date(2026, 7, 26))
    assert n1 == "VIS-20260726-000001"
    assert n2 == "VIS-20260726-000002"

    n3 = await gen.next_number(clinic_id, branch_id, date(2026, 7, 27))
    assert n3 == "VIS-20260727-000001"

    n4 = await gen.next_number(clinic_id, branch_id_2, date(2026, 7, 26))
    assert n4 == "VIS-20260726-000001"

    await db_session.rollback()


async def test_visit_number_generation_concurrency_safe(engine, db_session: AsyncSession) -> None:
    from datetime import date

    from app.services.visit_number_generator import VisitNumberGenerator

    clinic, branches = await _make_real_clinic_and_branches(db_session, count=1)
    clinic_id = clinic.id
    branch_id = branches[0].id
    today = date(2026, 7, 26)

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def _issue_one() -> str:
        async with session_maker() as session:
            number = await VisitNumberGenerator(session).next_number(clinic_id, branch_id, today)
            await session.commit()
            return number

    results = await asyncio.gather(*(_issue_one() for _ in range(20)))
    assert len(results) == len(set(results)) == 20
    expected = {f"VIS-20260726-{str(i).zfill(6)}" for i in range(1, 21)}
    assert set(results) == expected


async def test_visit_status_transitions_write_timeline_events(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    called = await client.patch(f"/api/v1/visits/{visit_id}/status", headers=headers, json={"status": "Called"})
    assert called.status_code == 200, called.text
    assert called.json()["status"] == "Called"

    in_consult = await client.patch(
        f"/api/v1/visits/{visit_id}/status", headers=headers, json={"status": "InConsultation"}
    )
    assert in_consult.status_code == 200
    assert in_consult.json()["consultation_start"] is not None

    completed = await client.patch(
        f"/api/v1/visits/{visit_id}/status", headers=headers, json={"status": "Completed"}
    )
    assert completed.status_code == 200
    detail = completed.json()
    assert detail["status"] == "Completed"
    assert detail["consultation_end"] is not None
    assert detail["check_out_time"] is not None

    event_types = [t["event_type"] for t in detail["timeline"]]
    assert "Called" in event_types
    assert "ConsultationStarted" in event_types
    assert "ConsultationFinished" in event_types

    invalid = await client.patch(f"/api/v1/visits/{visit_id}/status", headers=headers, json={"status": "Called"})
    assert invalid.status_code == 400


async def test_visit_search_filters(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    by_patient = await client.get("/api/v1/visits", headers=headers, params={"patient_id": deps["patient_id"]})
    assert by_patient.status_code == 200
    assert by_patient.json()["total"] == 1

    by_doctor = await client.get("/api/v1/visits", headers=headers, params={"doctor_id": deps["doctor_id"]})
    assert by_doctor.json()["total"] == 1

    by_status = await client.get("/api/v1/visits", headers=headers, params={"status": "Waiting"})
    assert by_status.json()["total"] == 1

    by_wrong_status = await client.get("/api/v1/visits", headers=headers, params={"status": "Completed"})
    assert by_wrong_status.json()["total"] == 0

    today = queue["queue_date"]
    by_date = await client.get(
        "/api/v1/visits", headers=headers, params={"date_from": today, "date_to": today}
    )
    assert by_date.json()["total"] == 1

    by_q = await client.get("/api/v1/visits", headers=headers, params={"q": "Dela Cruz"})
    assert by_q.json()["total"] == 1


async def test_visit_pagination(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))

    patient2 = await _make_patient(client, headers, first_name="Second", mobile="+639171234570")
    await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=patient2["id"]))

    page1 = await client.get("/api/v1/visits", headers=headers, params={"limit": 1, "offset": 0})
    assert page1.json()["total"] == 2
    assert len(page1.json()["items"]) == 1

    page2 = await client.get("/api/v1/visits", headers=headers, params={"limit": 1, "offset": 1})
    assert len(page2.json()["items"]) == 1
    assert page1.json()["items"][0]["id"] != page2.json()["items"][0]["id"]


async def test_patient_visit_history_endpoint(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    response = await client.get(f"/api/v1/patients/{deps['patient_id']}/visits", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == queue["visit_id"]
    assert body["items"][0]["queue_number"] == queue["queue_number"]


async def test_visit_tenant_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_queue_deps(client, headers_a)
    queue = (await client.post("/api/v1/queues", headers=headers_a, json=_queue_payload(deps_a))).json()

    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    response = await client.get(f"/api/v1/visits/{queue['visit_id']}", headers=headers_b)
    assert response.status_code == 404

    list_response = await client.get("/api/v1/visits", headers=headers_b)
    assert list_response.json()["total"] == 0


# --- Recent-records convention: newest visit_date first, date-range filter ---
# The frontend resolves Today/This Week/This Month/Custom presets into
# concrete `date_from`/`date_to` bounds before calling this same endpoint
# (see `resolveRecordDateRange` in `frontend/src/lib/date-range.ts`) - the
# backend only ever sees plain date bounds, so these tests exercise the
# bounds directly rather than re-deriving preset math server-side.

async def test_visit_search_sorts_by_visit_date_descending_not_created_at(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    """The primary sort must match the field the date filter itself applies
    to (visit_date) - a visit created later but with an earlier visit_date
    (e.g. backdated) must still sort as the OLDER record."""
    import uuid as _uuid
    from datetime import date as _date

    from app.models.visit import Visit

    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    queue_a = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    patient2 = await _make_patient(client, headers, first_name="Second", mobile="+639171234571")
    queue_b = (
        await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=patient2["id"]))
    ).json()

    # queue_b's visit was created AFTER queue_a's (later created_at), but
    # give it an EARLIER visit_date - if the endpoint still sorted by
    # created_at, queue_b would incorrectly appear first.
    visit_a = await db_session.get(Visit, _uuid.UUID(queue_a["visit_id"]))
    visit_b = await db_session.get(Visit, _uuid.UUID(queue_b["visit_id"]))

    visit_a.visit_date = _date(2026, 6, 10)
    visit_b.visit_date = _date(2026, 6, 1)
    await db_session.commit()

    resp = await client.get("/api/v1/visits", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [queue_a["visit_id"], queue_b["visit_id"]]


async def test_visit_date_range_filter_excludes_visits_outside_the_range(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    from app.models.visit import Visit
    from datetime import date as _date
    import uuid as _uuid

    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    queue_in = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    patient2 = await _make_patient(client, headers, first_name="Outside", mobile="+639171234572")
    queue_out = (
        await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=patient2["id"]))
    ).json()

    (await db_session.get(Visit, _uuid.UUID(queue_in["visit_id"]))).visit_date = _date(2026, 6, 15)
    (await db_session.get(Visit, _uuid.UUID(queue_out["visit_id"]))).visit_date = _date(2026, 7, 1)
    await db_session.commit()

    # "This Month" for June, resolved client-side, arrives as a plain range.
    resp = await client.get(
        "/api/v1/visits", headers=headers, params={"date_from": "2026-06-01", "date_to": "2026-06-30"}
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert [i["id"] for i in items] == [queue_in["visit_id"]]


async def test_visit_date_range_with_no_matching_visits_returns_empty(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))

    resp = await client.get(
        "/api/v1/visits", headers=headers, params={"date_from": "2020-01-01", "date_to": "2020-01-31"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


async def test_visit_date_range_combines_with_status_filter(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    """Status = Waiting AND This Month must both apply - not either/or."""
    from app.models.visit import Visit
    from datetime import date as _date
    import uuid as _uuid

    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    queue = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    visit = await db_session.get(Visit, _uuid.UUID(queue["visit_id"]))
    today = visit.visit_date

    matching = await client.get(
        "/api/v1/visits", headers=headers,
        params={"status": "Waiting", "date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert matching.json()["total"] == 1

    wrong_status = await client.get(
        "/api/v1/visits", headers=headers,
        params={"status": "Completed", "date_from": today.isoformat(), "date_to": today.isoformat()},
    )
    assert wrong_status.json()["total"] == 0


async def test_visit_search_uses_id_as_stable_tie_break_for_identical_visit_date_and_created_at(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    from app.models.visit import Visit
    from datetime import UTC, datetime
    import uuid as _uuid

    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    queue_a = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    patient2 = await _make_patient(client, headers, first_name="Tiebreak", mobile="+639171234573")
    queue_b = (
        await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=patient2["id"]))
    ).json()

    visit_a = await db_session.get(Visit, _uuid.UUID(queue_a["visit_id"]))
    visit_b = await db_session.get(Visit, _uuid.UUID(queue_b["visit_id"]))
    same_time = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    visit_a.created_at = same_time
    visit_b.created_at = same_time
    await db_session.commit()

    expected_first, expected_second = (
        (queue_a["visit_id"], queue_b["visit_id"])
        if queue_a["visit_id"] > queue_b["visit_id"]
        else (queue_b["visit_id"], queue_a["visit_id"])
    )

    resp = await client.get("/api/v1/visits", headers=headers)
    ids = [i["id"] for i in resp.json()["items"]]
    assert ids.index(expected_first) < ids.index(expected_second)


async def test_visit_tenant_isolation_holds_with_date_range_filter(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """A date range that matches records in ANOTHER clinic must not leak
    them into this clinic's filtered results."""
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_queue_deps(client, headers_a)
    await client.post("/api/v1/queues", headers=headers_a, json=_queue_payload(deps_a))

    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    from datetime import date

    today = date.today().isoformat()
    resp = await client.get(
        "/api/v1/visits", headers=headers_b, params={"date_from": today, "date_to": today}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


async def test_existing_queue_endpoints_still_work(client: AsyncClient, make_clinic_with_owner) -> None:
    """Regression check: Phase 5 queue list/status-transition/cancel/slip
    endpoints keep working unmodified after the Phase 6 visit hook.

    Phase 9 note: this test previously fetched the slip with no vitals
    recorded, which now correctly 400s - `QueueService.get_slip` enforces
    "vital signs must be taken before printing the queue ticket" as of the
    Reception Queue Workflow Improvements (Feature 1), a deliberate,
    documented, backend-enforced business rule (see the docstring on
    `get_slip` in `queue_service.py`) that simply postdates this test and
    was never backfilled here. This is a stale test expectation (Option
    B), not a production defect - the correct fix is to make the test
    follow the real intended workflow (record vitals before printing),
    exactly like `test_queues.py`'s own `_enter_vitals` helper already
    does for its own slip-related tests."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    listing = await client.get("/api/v1/queues", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    status_change = await client.patch(
        f"/api/v1/queues/{created['id']}/status", headers=headers, json={"status": "Called"}
    )
    assert status_change.status_code == 200
    assert status_change.json()["status"] == "Called"

    # Record vitals first - the real prerequisite `get_slip` enforces -
    # before attempting to print the slip.
    consultation = (
        await client.post(f"/api/v1/visits/{created['visit_id']}/consultation/open-for-reception", headers=headers)
    ).json()
    vitals = await client.put(
        f"/api/v1/consultations/{consultation['id']}/soap/subjective-objective",
        headers=headers,
        json={
            "blood_pressure": "120/80", "pulse_rate": 72, "respiratory_rate": 18,
            "temperature": 36.8, "height_cm": 170, "weight_kg": 65, "oxygen_saturation": 98,
        },
    )
    assert vitals.status_code == 200, vitals.text

    slip = await client.get(f"/api/v1/queues/{created['id']}/slip", headers=headers)
    assert slip.status_code == 200, slip.text
    assert slip.json()["queue_number"] == created["queue_number"]
    assert slip.json()["vitals_taken"] is True

    cancel = await client.post(f"/api/v1/queues/{created['id']}/cancel", headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "Cancelled"


async def test_slip_without_vitals_is_rejected_for_non_laboratory_tickets(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Phase 9 regression coverage: proves the intended, documented
    behavior this test file was missing direct coverage for - printing a
    non-Laboratory queue ticket's slip before vitals are recorded is
    rejected with a clear 400, not silently allowed."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    slip = await client.get(f"/api/v1/queues/{created['id']}/slip", headers=headers)
    assert slip.status_code == 400, slip.text
    assert "vital signs" in slip.json()["detail"].lower()
