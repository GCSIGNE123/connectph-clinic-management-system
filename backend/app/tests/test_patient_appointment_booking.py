"""Phase 19: Patient Self-Service Appointment Booking integration tests.

Covers the patient-facing booking router (`app/api/v1/patient_portal/appointments.py`):
reference data, availability, create/reschedule/cancel scoped to the
authenticated patient, 404-not-403 isolation from other patients' bookings,
reception-side visibility of a patient-booked appointment, and the critical
concurrency guarantee - two simultaneous create requests for the exact same
doctor/date/start_time must not both succeed, because the real guarantee is
the Postgres partial unique index `uq_appointments_doctor_slot_active`
(migration 0012), not an application-level check-then-insert.
"""

import asyncio
import uuid
from datetime import date as date_cls
from datetime import time as time_cls

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
    return {"branch_id": branch["id"], "department_id": department["id"], "doctor_id": doctor["id"], "service_id": service["id"]}


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


async def _create_patient_account(
    client: AsyncClient, headers: dict, *, first_name="Juan", last_name="Dela Cruz", mobile="+639171234567", email: str | None = None
) -> dict:
    """Creates a Patient (staff-side) with an email set (the patient portal
    logs in by `identifier` = the Patient's own email/mobile - see
    `PatientAuthService.login` -> `PatientAccountRepository.get_by_identifier`)."""
    email = email or f"patient-{uuid.uuid4().hex[:8]}@example.com"
    patient = (
        await client.post(
            "/api/v1/patients", headers=headers,
            json={
                "first_name": first_name, "last_name": last_name, "birth_date": "1990-05-15",
                "gender": "Male", "civil_status": "Single", "mobile_number": mobile, "email": email,
            },
        )
    ).json()["patient"]
    return patient


FUTURE_DATE = "2027-03-03"  # a Wednesday, safely in the future


async def _provision_patient_login(db_session: AsyncSession, *, clinic_id, patient_id, email: str, password: str = "PatientPass123!"):
    from app.core.security import hash_password as _hash
    from app.models.patient_account import PatientAccount

    account = PatientAccount(
        clinic_id=clinic_id, patient_id=patient_id,
        password_hash=_hash(password), is_email_verified=True, is_active=True,
    )
    db_session.add(account)
    await db_session.commit()
    return email, password


async def _patient_login(client: AsyncClient, identifier: str, password: str) -> dict:
    resp = await client.post("/api/v1/patient-portal/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["patient_id"]


async def test_patient_booking_flow_reschedule_cancel_and_reception_visibility(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
):
    clinic, owner, staff_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, staff_headers)
    await _set_schedule(client, staff_headers, deps["doctor_id"])
    patient = await _create_patient_account(client, staff_headers)
    email, password = await _provision_patient_login(
        db_session, clinic_id=clinic.id, patient_id=uuid.UUID(patient["id"]), email=patient["email"],
    )
    patient_headers, patient_id = await _patient_login(client, email, password)
    assert patient_id == patient["id"]

    # Reference data is patient-readable.
    branches = await client.get("/api/v1/patient-portal/appointments/branches", headers=patient_headers)
    assert branches.status_code == 200 and len(branches.json()) == 1
    doctors = await client.get("/api/v1/patient-portal/appointments/doctors", headers=patient_headers)
    assert doctors.status_code == 200 and len(doctors.json()) == 1

    # Availability reflects the configured schedule.
    avail = await client.get(
        "/api/v1/patient-portal/appointments/availability",
        headers=patient_headers,
        params={"doctor_id": deps["doctor_id"], "date_from": FUTURE_DATE, "date_to": FUTURE_DATE},
    )
    assert avail.status_code == 200, avail.text
    assert FUTURE_DATE in avail.json()["dates"]

    slots = await client.get(
        f"/api/v1/patient-portal/appointments/availability/{FUTURE_DATE}",
        headers=patient_headers, params={"doctor_id": deps["doctor_id"]},
    )
    assert slots.status_code == 200
    assert any(s["start_time"] == "08:00:00" for s in slots.json()["slots"])

    # Book.
    create_resp = await client.post(
        "/api/v1/patient-portal/appointments",
        headers=patient_headers,
        json={
            "branch_id": deps["branch_id"], "doctor_id": deps["doctor_id"], "department_id": deps["department_id"],
            "service_id": deps["service_id"], "appointment_type": "NewConsultation",
            "appointment_date": FUTURE_DATE, "start_time": "08:00:00",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    booked = create_resp.json()
    assert booked["status"] == "Booked"
    appointment_id = booked["id"]

    # Shows up in the patient's own list.
    mine = await client.get("/api/v1/patient-portal/appointments", headers=patient_headers)
    assert mine.status_code == 200
    assert any(a["id"] == appointment_id for a in mine.json())

    # --- Reception integration: same table, visible via the STAFF endpoints ---
    staff_search = await client.get("/api/v1/appointments", headers=staff_headers, params={"q": booked["appointment_number"]})
    assert staff_search.status_code == 200, staff_search.text
    staff_items = staff_search.json()["items"]
    assert any(i["id"] == appointment_id for i in staff_items), "patient-booked appointment not visible via staff search"

    staff_by_patient_name = await client.get("/api/v1/appointments", headers=staff_headers, params={"q": "Dela Cruz"})
    assert any(i["id"] == appointment_id for i in staff_by_patient_name.json()["items"])
    staff_by_doctor = await client.get("/api/v1/appointments", headers=staff_headers, params={"doctor_id": deps["doctor_id"]})
    assert any(i["id"] == appointment_id for i in staff_by_doctor.json()["items"])
    staff_by_date = await client.get(
        "/api/v1/appointments", headers=staff_headers, params={"date_from": FUTURE_DATE, "date_to": FUTURE_DATE}
    )
    assert any(i["id"] == appointment_id for i in staff_by_date.json()["items"])

    # Staff check-in still auto-creates a linked Queue + Visit.
    checkin = await client.post(f"/api/v1/appointments/{appointment_id}/check-in", headers=staff_headers)
    assert checkin.status_code == 200, checkin.text
    checked = checkin.json()
    assert checked["queue_id"] is not None
    assert checked["visit_id"] is not None
    queue_resp = await client.get(f"/api/v1/queues/{checked['queue_id']}", headers=staff_headers)
    assert queue_resp.status_code == 200
    assert queue_resp.json()["patient_id"] == patient["id"]
    visit_resp = await client.get(f"/api/v1/visits/{checked['visit_id']}", headers=staff_headers)
    assert visit_resp.status_code == 200
    assert visit_resp.json()["patient_id"] == patient["id"]


async def test_patient_reschedule_and_cancel_and_isolation(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession):
    clinic, owner, staff_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, staff_headers)
    await _set_schedule(client, staff_headers, deps["doctor_id"])

    patient_a = await _create_patient_account(client, staff_headers, first_name="Ana", last_name="Reyes", mobile="+639170000001")
    email_a, pass_a = await _provision_patient_login(
        db_session, clinic_id=clinic.id, patient_id=uuid.UUID(patient_a["id"]), email=patient_a["email"],
    )
    headers_a, _ = await _patient_login(client, email_a, pass_a)

    patient_b = await _create_patient_account(client, staff_headers, first_name="Beth", last_name="Santos", mobile="+639170000002")
    email_b, pass_b = await _provision_patient_login(
        db_session, clinic_id=clinic.id, patient_id=uuid.UUID(patient_b["id"]), email=patient_b["email"],
    )
    headers_b, _ = await _patient_login(client, email_b, pass_b)

    create_resp = await client.post(
        "/api/v1/patient-portal/appointments", headers=headers_a,
        json={
            "branch_id": deps["branch_id"], "doctor_id": deps["doctor_id"], "department_id": deps["department_id"],
            "service_id": deps["service_id"], "appointment_type": "NewConsultation",
            "appointment_date": FUTURE_DATE, "start_time": "08:30:00",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    appointment_id = create_resp.json()["id"]

    # Patient B cannot see or mutate Patient A's appointment - 404, not 403/200.
    b_reschedule = await client.patch(
        f"/api/v1/patient-portal/appointments/{appointment_id}/reschedule", headers=headers_b,
        json={"appointment_date": FUTURE_DATE, "start_time": "09:00:00"},
    )
    assert b_reschedule.status_code == 404
    b_cancel = await client.post(f"/api/v1/patient-portal/appointments/{appointment_id}/cancel", headers=headers_b, json={})
    assert b_cancel.status_code == 404

    # Patient A can reschedule her own appointment.
    a_reschedule = await client.patch(
        f"/api/v1/patient-portal/appointments/{appointment_id}/reschedule", headers=headers_a,
        json={"appointment_date": FUTURE_DATE, "start_time": "09:00:00", "reason": "Conflict"},
    )
    assert a_reschedule.status_code == 200, a_reschedule.text
    new_appointment_id = a_reschedule.json()["id"]
    assert a_reschedule.json()["start_time"] == "09:00:00"

    a_cancel = await client.post(
        f"/api/v1/patient-portal/appointments/{new_appointment_id}/cancel", headers=headers_a, json={"reason": "Changed my mind"}
    )
    assert a_cancel.status_code == 200
    assert a_cancel.json()["status"] == "Cancelled"

    # Audit trail attributes the actions to the patient, not a staff user.
    from app.models.audit_log import AuditLog

    rows = (
        await db_session.execute(
            select(AuditLog).where(AuditLog.clinic_id == clinic.id, AuditLog.action.like("appointment.%"))
        )
    ).scalars().all()
    patient_events = [r for r in rows if r.user_id is None and r.metadata_json and r.metadata_json.get("principal") == "patient"]
    assert any(r.action == "appointment.created" for r in patient_events)
    assert any(r.action == "appointment.rescheduled" for r in patient_events)
    assert any(r.action == "appointment.cancelled" for r in patient_events)


async def test_concurrent_patient_bookings_same_slot_only_one_succeeds(
    engine, make_clinic_with_owner, db_session: AsyncSession, client: AsyncClient
):
    """The core race-condition requirement: two concurrent booking requests
    for the same doctor+date+time must not both succeed. Uses two genuinely
    independent AsyncSessions (and therefore independent Postgres
    connections/transactions) against the same `engine`, firing
    `AppointmentService.create_patient_appointment` concurrently via
    `asyncio.gather` - a real race, not a sequential simulation. The
    assertion is that exactly one call succeeds and the other gets a 409
    from the partial unique index `uq_appointments_doctor_slot_active`
    (migration 0012), never a 500/duplicate row.
    """
    clinic, owner, staff_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_deps(client, staff_headers)
    await _set_schedule(client, staff_headers, deps["doctor_id"])
    patient = await _create_patient_account(client, staff_headers)
    patient_id = uuid.UUID(patient["id"])
    clinic_id = clinic.id

    from app.schemas.appointment import AppointmentCreate
    from app.services.appointment_service import AppointmentService

    payload = AppointmentCreate(
        patient_id=patient_id, branch_id=uuid.UUID(deps["branch_id"]), doctor_id=uuid.UUID(deps["doctor_id"]),
        department_id=uuid.UUID(deps["department_id"]), service_id=uuid.UUID(deps["service_id"]),
        appointment_type="NewConsultation", appointment_date="2027-03-03", start_time="08:00:00",
    )

    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async def _attempt():
        async with session_maker() as session:
            service = AppointmentService(session)
            try:
                detail = await service.create_patient_appointment(payload, clinic_id=clinic_id, patient_id=patient_id)
                return ("ok", detail.id)
            except Exception as exc:  # noqa: BLE001 - we want the HTTPException detail/status too
                status_code = getattr(exc, "status_code", None)
                return ("error", status_code, f"{type(exc).__module__}.{type(exc).__name__}: {exc}")

    results = await asyncio.gather(_attempt(), _attempt())

    successes = [r for r in results if r[0] == "ok"]
    failures = [r for r in results if r[0] == "error"]

    assert len(successes) == 1, f"expected exactly one booking to succeed, got: {results}"
    assert len(failures) == 1, f"expected exactly one booking to be rejected, got: {results}"
    assert failures[0][1] == 409, f"the losing request must get a 409 Conflict (DB unique-violation translated cleanly), got: {results}"

    # Confirm only ONE row actually exists for that doctor/date/time.
    from app.models.appointment import Appointment

    async with session_maker() as verify_session:
        rows = (
            await verify_session.execute(
                select(Appointment).where(
                    Appointment.clinic_id == clinic_id, Appointment.doctor_id == uuid.UUID(deps["doctor_id"]),
                    Appointment.appointment_date == date_cls(2027, 3, 3), Appointment.start_time == time_cls(8, 0, 0),
                )
            )
        ).scalars().all()
        assert len(rows) == 1, f"expected exactly one appointment row for the contested slot, found {len(rows)}"
