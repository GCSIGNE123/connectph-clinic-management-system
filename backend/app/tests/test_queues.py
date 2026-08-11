"""Integration tests for Phase 5 Reception & Queue Management: create,
number generation (sequential/daily-reset/concurrency-safe), duplicate-active
rejection, inactive doctor/department/service rejection, archived-patient
rejection, status transitions + history, list/search/filter, tenant isolation.
"""

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.dependencies import get_db
from app.core.security import hash_password
from app.main import app
from app.models.role import Role

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    """Reception Queue Workflow Improvements added several new tests to this
    file that each log in via the real endpoint, which pushed this file's
    own login count past `RATE_LIMIT_LOGIN_MAX_ATTEMPTS` within a single
    ~60s pytest run - the same shared, real, non-test-mode-bypassed limiter
    documented as BUG-034 (there, the trigger is combining this file with
    OTHER login-heavy files in one run; here it's this file alone getting
    large enough). Reusing the exact same per-test reset already used by
    `test_tv_display.py`/`test_billing.py`/etc. rather than inventing a new
    workaround - this only affects test isolation, no production code path."""
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


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, password: str = "TestPass123!"):
    """Same pattern used across the rest of the suite (e.g. `test_tv_display.py`,
    `test_billing.py`) - creates a real user of the given role directly via
    the DB session (no HTTP round-trip needed for setup) and returns its
    login email."""
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"{role_name.lower()}-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"{role_name.lower()}{suffix}", hashed_password=hash_password(password),
        first_name="Test", last_name=role_name, role_id=role.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return email, user


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


async def _enter_vitals(client: AsyncClient, headers: dict, visit_id: str) -> None:
    """Reception Queue Workflow Improvements (Feature 1): records all
    required vitals for a Queue ticket's linked Visit via the real
    Receptionist-facing endpoints (`open-for-reception` +
    `soap/subjective-objective`), the same path `ReceptionVitalsDialog`
    uses in the browser - not a direct DB write."""
    consultation = (
        await client.post(f"/api/v1/visits/{visit_id}/consultation/open-for-reception", headers=headers)
    ).json()
    response = await client.put(
        f"/api/v1/consultations/{consultation['id']}/soap/subjective-objective",
        headers=headers,
        json={
            "blood_pressure": "120/80",
            "pulse_rate": 72,
            "respiratory_rate": 18,
            "temperature": 36.8,
            "height_cm": 170,
            "weight_kg": 65,
            "oxygen_saturation": 98,
        },
    )
    assert response.status_code == 200, response.text


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


async def test_list_queues_reports_vitals_taken_per_ticket(client: AsyncClient, make_clinic_with_owner) -> None:
    """The Reception Queue list exposes `vitals_taken` per ticket (drives
    the "Enter Vitals" button's color) - false before vitals are entered,
    true immediately after, computed from the same required-fields rule
    already enforced at print time. No visit at all -> false, not an error."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    before = await client.get("/api/v1/queues", headers=headers)
    assert before.status_code == 200
    item_before = next(i for i in before.json()["items"] if i["id"] == created["id"])
    assert item_before["vitals_taken"] is False

    await _enter_vitals(client, headers, created["visit_id"])

    after = await client.get("/api/v1/queues", headers=headers)
    item_after = next(i for i in after.json()["items"] if i["id"] == created["id"])
    assert item_after["vitals_taken"] is True


async def test_patient_yakap_flag_defaults_false_and_persists(client: AsyncClient, make_clinic_with_owner) -> None:
    """Phase 2.7: `Patient.is_yakap_beneficiary` defaults False for existing-
    style patient creation, and a patient explicitly marked YAKAP persists
    that flag across a fresh GET (proxy for "survives refresh/logout")."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)

    regular = (
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Regular",
                "last_name": "Patient",
                "birth_date": "1990-01-01",
                "gender": "Male",
                "civil_status": "Single",
                "mobile_number": "+639170000001",
            },
        )
    ).json()["patient"]
    assert regular["is_yakap_beneficiary"] is False

    yakap = (
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Yakap",
                "last_name": "Patient",
                "birth_date": "1990-01-01",
                "gender": "Female",
                "civil_status": "Single",
                "mobile_number": "+639170000002",
                "is_yakap_beneficiary": True,
            },
        )
    ).json()["patient"]
    assert yakap["is_yakap_beneficiary"] is True

    refetched = (await client.get(f"/api/v1/patients/{yakap['id']}", headers=headers)).json()
    assert refetched["is_yakap_beneficiary"] is True


async def test_queue_ticket_preserves_visit_classification_independent_of_prefix(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Phase 2.7: YAKAP/Regular is a classification, NOT a queue prefix -
    two tickets in the same A-prefix bucket, one YAKAP and one Regular,
    still get plain sequential A001/A002 numbers with no Y-prefix and no
    numbering disruption."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)

    yakap_ticket = (
        await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit_classification="Yakap"))
    ).json()
    assert yakap_ticket["queue_number"] == "A001"
    assert yakap_ticket["queue_prefix"] == "A"
    assert yakap_ticket["visit_classification"] == "Yakap"

    patient2 = (
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Second", "last_name": "Patient", "birth_date": "1991-02-02",
                "gender": "Female", "civil_status": "Single", "mobile_number": "+639170000003",
            },
        )
    ).json()["patient"]
    regular_ticket = (
        await client.post(
            "/api/v1/queues",
            headers=headers,
            json=_queue_payload(deps, patient_id=patient2["id"], visit_classification="Regular"),
        )
    ).json()
    assert regular_ticket["queue_number"] == "A002"
    assert regular_ticket["queue_prefix"] == "A"
    assert regular_ticket["visit_classification"] == "Regular"


async def test_queue_visit_classification_defaults_regular_when_omitted(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """A raw `POST /queues` call that omits `visit_classification` entirely
    (e.g. an older/unaware client) still succeeds and defaults to Regular -
    fully backward compatible."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    assert created["visit_classification"] == "Regular"


async def test_queue_filter_by_visit_classification(client: AsyncClient, make_clinic_with_owner) -> None:
    """Filtering by classification is view-only - does not alter queue
    numbers, prefixes, or ticket state."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, visit_classification="Yakap"))

    patient2 = (
        await client.post(
            "/api/v1/patients",
            headers=headers,
            json={
                "first_name": "Filter", "last_name": "Test", "birth_date": "1992-03-03",
                "gender": "Male", "civil_status": "Single", "mobile_number": "+639170000004",
            },
        )
    ).json()["patient"]
    await client.post(
        "/api/v1/queues",
        headers=headers,
        json=_queue_payload(deps, patient_id=patient2["id"], visit_classification="Regular"),
    )

    yakap_only = await client.get(
        "/api/v1/queues", headers=headers, params={"visit_classification": "Yakap"}
    )
    assert yakap_only.status_code == 200
    yakap_body = yakap_only.json()
    assert yakap_body["total"] == 1
    assert yakap_body["items"][0]["queue_number"] == "A001"

    regular_only = await client.get(
        "/api/v1/queues", headers=headers, params={"visit_classification": "Regular"}
    )
    regular_body = regular_only.json()
    assert regular_body["total"] == 1
    assert regular_body["items"][0]["queue_number"] == "A002"

    all_tickets = await client.get("/api/v1/queues", headers=headers)
    assert all_tickets.json()["total"] == 2


async def test_queue_slip_payload(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    await _enter_vitals(client, headers, created["visit_id"])

    response = await client.get(f"/api/v1/queues/{created['id']}/slip", headers=headers)
    assert response.status_code == 200
    slip = response.json()
    assert slip["queue_number"] == "A001"
    assert slip["patient_name"]
    assert slip["qr_token"]
    assert slip["vitals_taken"] is True


async def test_queue_slip_blocked_without_vitals(client: AsyncClient, make_clinic_with_owner) -> None:
    """Feature 1 (Reception Queue Workflow Improvements): printing (fetching
    the slip) is rejected with a clear, real backend error - not merely a
    disabled frontend button - when the ticket's linked visit has no vitals
    recorded yet. A raw API call (bypassing any frontend button state)
    still gets blocked."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    response = await client.get(f"/api/v1/queues/{created['id']}/slip", headers=headers)
    assert response.status_code == 400, response.text
    assert "vital signs" in response.json()["detail"].lower()


async def test_queue_slip_succeeds_after_vitals_entered(client: AsyncClient, make_clinic_with_owner) -> None:
    """Same ticket: blocked before vitals, then printable immediately after -
    proves the gate re-evaluates live state rather than caching a stale
    rejection, and that vitals is the only thing standing in the way."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    blocked = await client.get(f"/api/v1/queues/{created['id']}/slip", headers=headers)
    assert blocked.status_code == 400

    await _enter_vitals(client, headers, created["visit_id"])

    allowed = await client.get(f"/api/v1/queues/{created['id']}/slip", headers=headers)
    assert allowed.status_code == 200
    assert allowed.json()["vitals_taken"] is True


async def test_queue_call_and_reannounce(client: AsyncClient, make_clinic_with_owner) -> None:
    """Feature 3: Owner (a role in `QUEUE_TRANSITION_ROLES`) calls a Waiting
    ticket via the existing status-transition endpoint (Waiting -> Called),
    then re-announces it via the new endpoint - queue number, ticket id, and
    history/status stay exactly the same across the re-announce; only
    `called_at` moves forward, which is what the announcement/TV-display
    re-fire mechanism already keys off of."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    queue_id = created["id"]

    called = await client.patch(f"/api/v1/queues/{queue_id}/status", headers=headers, json={"status": "Called"})
    assert called.status_code == 200, called.text
    called_body = called.json()
    assert called_body["status"] == "Called"
    assert called_body["queue_number"] == "A001"
    first_called_at = called_body["called_at"]
    assert first_called_at is not None

    reannounced = await client.post(f"/api/v1/queues/{queue_id}/reannounce", headers=headers)
    assert reannounced.status_code == 200, reannounced.text
    reannounced_body = reannounced.json()
    assert reannounced_body["id"] == queue_id
    assert reannounced_body["queue_number"] == "A001"
    assert reannounced_body["status"] == "Called"
    assert reannounced_body["called_at"] >= first_called_at

    # Re-announcing did not create a second ticket.
    all_today = await client.get("/api/v1/queues", headers=headers)
    assert all_today.json()["total"] == 1


async def test_reannounce_requires_already_called(client: AsyncClient, make_clinic_with_owner) -> None:
    """A ticket still Waiting has nothing to re-announce yet."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()

    response = await client.post(f"/api/v1/queues/{created['id']}/reannounce", headers=headers)
    assert response.status_code == 400


async def test_cashier_cannot_call_or_reannounce(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    """RBAC: Cashier must not gain queue-calling permissions it never had -
    `QUEUE_TRANSITION_ROLES` (Owner/Administrator/Receptionist/Doctor/Nurse)
    is unchanged by this feature, and the new `/reannounce` endpoint reuses
    that exact same dependency."""
    clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)
    created = (await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps))).json()
    await client.patch(f"/api/v1/queues/{created['id']}/status", headers=headers, json={"status": "Called"})

    cashier_password = "SuperSecret123!"
    cashier_email, _cashier_user = await _make_role_login(
        db_session, clinic_id=clinic.id, role_name="Cashier", password=cashier_password
    )
    cashier_token = await _login(client, clinic.slug, cashier_email, cashier_password)
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    call_attempt = await client.patch(
        f"/api/v1/queues/{created['id']}/status", headers=cashier_headers, json={"status": "Called"}
    )
    assert call_attempt.status_code == 403

    reannounce_attempt = await client.post(f"/api/v1/queues/{created['id']}/reannounce", headers=cashier_headers)
    assert reannounce_attempt.status_code == 403


async def test_doctor_scoped_prefix_override_and_independent_sequencing(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Post-RC1 (Multi-Department/Multi-Doctor TV Queue Display): a doctor-
    specific `QueueSetting` override (doctor_id set, no department_id)
    resolves ahead of the clinic-wide default for that doctor's own queue
    tickets, and each prefix's numbering stays independently sequenced -
    Dr. B's tickets never perturb Dr. A's (or the clinic-wide "A" default's)
    counter, mirroring the existing department-override behaviour one level
    narrower."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, headers)  # doctor here keeps the clinic-wide "A" default

    doctor_b = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Maria", "last_name": "Santos"})
    ).json()

    # Note: `QueueSetting` resolution requires an exact match on whichever
    # branch_id/department_id the queue-creation call is itself scoped to
    # (see `QueueSettingRepository.get_effective_for_doctor` -> `get_for_branch`),
    # so a doctor override that should apply to tickets in this branch and
    # department must be created with those same real ids, not NULL - NULL
    # branch/department only match a resolve call that itself passes NULL
    # (the true clinic-wide case).
    override = await client.put(
        "/api/v1/queue-settings",
        headers=headers,
        json={
            "branch_id": deps["branch_id"],
            "department_id": deps["department_id"],
            "doctor_id": doctor_b["id"],
            "queue_prefix": "B",
            "max_daily_queue": 50,
            "reset_time": "00:00",
            "allow_walkins": True,
            "allow_priority_lane": True,
        },
    )
    assert override.status_code == 200, override.text
    assert override.json()["queue_prefix"] == "B"

    # The override upsert is keyed on the full branch/department/doctor
    # scope (not just branch_id) - it must show up as its own row, distinct
    # from any clinic-wide default row (there is none yet for a fresh
    # clinic; the hardcoded "A" fallback applies until one is created).
    listing = await client.get("/api/v1/queue-settings", headers=headers)
    assert listing.status_code == 200
    prefixes = {(s["department_id"], s["doctor_id"]): s["queue_prefix"] for s in listing.json()["items"]}
    assert prefixes[(deps["department_id"], doctor_b["id"])] == "B"

    def _patient_payload(first: str, last: str, mobile: str) -> dict:
        return {
            "first_name": first, "last_name": last, "birth_date": "1990-01-01",
            "gender": "Male", "civil_status": "Single", "mobile_number": mobile,
        }

    async def _new_patient(first: str, last: str, mobile: str) -> str:
        resp = await client.post("/api/v1/patients", headers=headers, json=_patient_payload(first, last, mobile))
        return resp.json()["patient"]["id"]

    p1 = await _new_patient("A", "One", "+639170000001")
    p2 = await _new_patient("B", "One", "+639170000002")
    p3 = await _new_patient("A", "Two", "+639170000003")
    p4 = await _new_patient("B", "Two", "+639170000004")

    qa1 = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=p1))
    qb1 = await client.post(
        "/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=p2, doctor_id=doctor_b["id"])
    )
    qa2 = await client.post("/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=p3))
    qb2 = await client.post(
        "/api/v1/queues", headers=headers, json=_queue_payload(deps, patient_id=p4, doctor_id=doctor_b["id"])
    )

    assert qa1.json()["queue_number"] == "A001"
    assert qb1.json()["queue_number"] == "B001"
    assert qa2.json()["queue_number"] == "A002"
    assert qb2.json()["queue_number"] == "B002"


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
