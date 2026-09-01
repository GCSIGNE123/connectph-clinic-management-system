"""Integration tests for Phase 11 Appointment Management: slot-validated
create (rejects double-booking / outside-hours / during-break); confirm;
reschedule (validates new slot, writes history with old/new values);
cancel + waitlist offer; check-in creates a REAL linked Queue AND Visit by
reusing `QueueService.create_queue()` (asserts patient/doctor/department
match and the queue-number format is the standard `A00N`); complete;
no-show; role gating; patient-appointments and doctor-schedule endpoints;
tenant isolation.
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


async def _setup_deps(client: AsyncClient, headers: dict) -> dict:
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
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


async def _set_schedule(client: AsyncClient, headers: dict, doctor_id: str) -> None:
    days = [
        {
            "day_of_week": d, "start_time": "08:00:00", "end_time": "12:00:00",
            "lunch_break_start": "10:00:00", "lunch_break_end": "10:15:00",
            "slot_duration_minutes": 30, "max_patients_per_day": 10, "is_active": True,
        }
        for d in range(7)
    ]
    resp = await client.put(f"/api/v1/doctors/{doctor_id}/schedule", headers=headers, json={"days": days})
    assert resp.status_code == 200, resp.text


def _apt_payload(deps: dict, *, appointment_date: str, start_time: str) -> dict:
    return {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "doctor_id": deps["doctor_id"],
        "department_id": deps["department_id"], "service_id": deps["service_id"],
        "appointment_type": "NewConsultation", "appointment_date": appointment_date, "start_time": start_time,
    }


# A Wednesday, safely in the future relative to any plausible test-run date.
FUTURE_DATE = "2027-03-03"


async def test_create_and_slot_validation(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])

    ok = await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="08:30:00"))
    assert ok.status_code == 200, ok.text
    assert ok.json()["appointment_number"].startswith("APT-")
    assert ok.json()["end_time"] == "09:00:00"

    dup = await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="08:30:00"))
    assert dup.status_code == 409, dup.text

    outside = await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="13:00:00"))
    assert outside.status_code == 400, outside.text

    lunch = await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="10:00:00"))
    assert lunch.status_code == 400, lunch.text

    holiday_resp = await client.post(
        "/api/v1/holidays", headers=headers, json={"holiday_name": "Test Holiday", "date": "2027-03-10", "is_closed": True},
    )
    assert holiday_resp.status_code in (200, 201), holiday_resp.text
    on_holiday = await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date="2027-03-10", start_time="08:30:00"))
    assert on_holiday.status_code == 400, on_holiday.text

    block_resp = await client.post(
        f"/api/v1/doctors/{deps['doctor_id']}/schedule/blocks", headers=headers,
        json={"block_date": "2027-03-11", "block_type": "Vacation", "reason": "Leave"},
    )
    assert block_resp.status_code == 200, block_resp.text
    on_block = await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date="2027-03-11", start_time="08:30:00"))
    assert on_block.status_code == 400, on_block.text


async def test_confirm_and_reschedule_writes_history(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])

    created = (await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"))).json()
    apt_id = created["id"]

    confirmed = await client.patch(f"/api/v1/appointments/{apt_id}/confirm", headers=headers)
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "Confirmed"

    rescheduled = await client.patch(
        f"/api/v1/appointments/{apt_id}/reschedule", headers=headers,
        json={"appointment_date": FUTURE_DATE, "start_time": "09:30:00", "reason": "Doctor unavailable"},
    )
    assert rescheduled.status_code == 200, rescheduled.text
    new_apt = rescheduled.json()
    assert new_apt["id"] != apt_id
    assert new_apt["start_time"] == "09:30:00"
    assert new_apt["status"] == "Booked"

    old_detail = (await client.get(f"/api/v1/appointments/{apt_id}", headers=headers)).json()
    assert old_detail["status"] == "Rescheduled"
    reschedule_entries = [h for h in old_detail["history"] if h["action"] == "Rescheduled"]
    assert len(reschedule_entries) == 1
    assert "09:00:00" in reschedule_entries[0]["from_value"]
    assert "09:30:00" in reschedule_entries[0]["to_value"]


async def test_check_in_creates_linked_queue_and_visit(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])

    created = (await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"))).json()
    apt_id = created["id"]

    checked_in = await client.post(f"/api/v1/appointments/{apt_id}/check-in", headers=headers)
    assert checked_in.status_code == 200, checked_in.text
    body = checked_in.json()
    assert body["status"] == "CheckedIn"
    assert body["queue_id"] is not None
    assert body["visit_id"] is not None

    queue_resp = await client.get(f"/api/v1/queues/{body['queue_id']}", headers=headers)
    assert queue_resp.status_code == 200
    queue = queue_resp.json()
    assert queue["patient_id"] == deps["patient_id"]
    assert queue["doctor_id"] == deps["doctor_id"]
    assert queue["department_id"] == deps["department_id"]
    assert queue["visit_id"] == body["visit_id"]
    # Standard queue-number format (prefix + zero-padded number), same as walk-ins.
    assert queue["queue_number"][0].isalpha()
    assert queue["queue_number"][1:].isdigit()

    visit_resp = await client.get(f"/api/v1/visits/{body['visit_id']}", headers=headers)
    assert visit_resp.status_code == 200
    visit = visit_resp.json()
    assert visit["patient_id"] == deps["patient_id"]
    assert visit["doctor_id"] == deps["doctor_id"]
    assert visit["queue_id"] == body["queue_id"]
    assert visit["visit_type"] == "Appointment"

    event_types = [e["event_type"] for e in visit["timeline"]]
    assert "AppointmentCheckedIn" in event_types

    history = (await client.get(f"/api/v1/appointments/{apt_id}/history", headers=headers)).json()
    assert any(h["action"] == "CheckedIn" for h in history)


async def test_complete_and_no_show(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])

    created = (await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"))).json()
    checked_in = (await client.post(f"/api/v1/appointments/{created['id']}/check-in", headers=headers)).json()
    completed = await client.patch(f"/api/v1/appointments/{checked_in['id']}/complete", headers=headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "Completed"

    created2 = (await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:30:00"))).json()
    no_show = await client.patch(f"/api/v1/appointments/{created2['id']}/no-show", headers=headers)
    assert no_show.status_code == 200
    assert no_show.json()["status"] == "NoShow"


async def test_cancel_offers_waitlist_slot(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])

    created = (await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"))).json()

    # A second patient joins the waitlist for this doctor/date range.
    patient2 = (
        await client.post(
            "/api/v1/patients", headers=headers,
            json={
                "first_name": "Maria", "last_name": "Reyes", "birth_date": "1985-02-01",
                "gender": "Female", "civil_status": "Single", "mobile_number": "+639171234568",
            },
        )
    ).json()["patient"]

    cancelled = await client.patch(f"/api/v1/appointments/{created['id']}/cancel", headers=headers, json={"reason": "Patient unavailable"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "Cancelled"

    # Slot is free again after cancellation.
    slots = await client.get(f"/api/v1/doctors/{deps['doctor_id']}/available-slots", headers=headers, params={"date": FUTURE_DATE})
    assert slots.status_code == 200
    freed = next(s for s in slots.json()["slots"] if s["start_time"] == "09:00:00")
    assert freed["is_available"] is True


async def test_role_gating(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession):
    clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])

    recep_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}

    doc_email, _ = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    # Doctor cannot create.
    doc_create = await client.post("/api/v1/appointments", headers=doc_headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"))
    assert doc_create.status_code == 403

    # Reception creates + checks in successfully.
    recep_create = await client.post("/api/v1/appointments", headers=recep_headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"))
    assert recep_create.status_code == 200, recep_create.text
    apt_id = recep_create.json()["id"]

    recep_checkin = await client.post(f"/api/v1/appointments/{apt_id}/check-in", headers=recep_headers)
    assert recep_checkin.status_code == 200, recep_checkin.text

    # Doctor cannot check-in another appointment, but can complete this one.
    created2 = (await client.post("/api/v1/appointments", headers=recep_headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:30:00"))).json()
    doc_checkin = await client.post(f"/api/v1/appointments/{created2['id']}/check-in", headers=doc_headers)
    assert doc_checkin.status_code == 403

    doc_complete = await client.patch(f"/api/v1/appointments/{apt_id}/complete", headers=doc_headers)
    assert doc_complete.status_code == 200, doc_complete.text


async def test_patient_appointments_and_doctor_schedule_endpoints(client: AsyncClient, make_clinic_with_owner):
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])

    await client.post("/api/v1/appointments", headers=headers, json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"))

    tab = await client.get(f"/api/v1/patients/{deps['patient_id']}/appointments", headers=headers)
    assert tab.status_code == 200
    assert len(tab.json()["upcoming"]) == 1

    schedule = await client.get(f"/api/v1/doctors/{deps['doctor_id']}/schedule", headers=headers)
    assert schedule.status_code == 200
    assert len(schedule.json()["days"]) == 7


async def test_tenant_isolation(client: AsyncClient, make_clinic_with_owner):
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup_deps(client, headers_a)
    await _set_schedule(client, headers_a, deps_a["doctor_id"])
    created = (await client.post("/api/v1/appointments", headers=headers_a, json=_apt_payload(deps_a, appointment_date=FUTURE_DATE, start_time="09:00:00"))).json()

    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    cross = await client.get(f"/api/v1/appointments/{created['id']}", headers=headers_b)
    assert cross.status_code == 404


# --- Recent-records convention: date-range filter on the patient history tab ---
# Appointments' own MAIN schedule list intentionally stays soonest-first
# (appointment_date ASC) - a forward-looking schedule, not a "recent
# activity" log - so only the date-range filter is added there; sort order
# is untouched (see `AppointmentRepository.search`, unchanged). The patient
# history tab's own upcoming/completed/cancelled/no_show status bucketing
# (also untouched) applies AFTER the date filter below.

async def test_patient_appointments_date_range_filter_excludes_outside_the_range(
    client: AsyncClient, make_clinic_with_owner
):
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])
    await client.post(
        "/api/v1/appointments", headers=headers,
        json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"),
    )

    in_range = await client.get(
        f"/api/v1/patients/{deps['patient_id']}/appointments", headers=headers,
        params={"date_from": "2027-03-01", "date_to": "2027-03-31"},
    )
    assert in_range.status_code == 200, in_range.text
    assert len(in_range.json()["upcoming"]) == 1

    out_of_range = await client.get(
        f"/api/v1/patients/{deps['patient_id']}/appointments", headers=headers,
        params={"date_from": "2020-01-01", "date_to": "2020-01-31"},
    )
    assert out_of_range.status_code == 200, out_of_range.text
    assert all(len(v) == 0 for v in out_of_range.json().values())


async def test_patient_appointments_date_range_does_not_disturb_status_bucketing(
    client: AsyncClient, make_clinic_with_owner
):
    """The status bucketing (upcoming/completed/cancelled/no_show) is
    computed AFTER the date filter - a matched appointment still lands in
    the correct bucket, not flattened into one list."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, headers)
    await _set_schedule(client, headers, deps["doctor_id"])
    await client.post(
        "/api/v1/appointments", headers=headers,
        json=_apt_payload(deps, appointment_date=FUTURE_DATE, start_time="09:00:00"),
    )

    resp = await client.get(
        f"/api/v1/patients/{deps['patient_id']}/appointments", headers=headers,
        params={"date_from": "2027-01-01", "date_to": "2027-12-31"},
    )
    body = resp.json()
    assert len(body["upcoming"]) == 1
    assert body["completed"] == []
    assert body["cancelled"] == []
    assert body["no_show"] == []
