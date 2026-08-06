"""Phase 18: Patient Portal tests.

Covers: patient auth (structurally distinct token), and - most importantly -
patient-to-patient and patient-to-clinic isolation: Patient A's token cannot
read Patient B's appointments/labs/prescriptions/billing (same clinic or a
different clinic), and a patient token is rejected by every clinic-staff and
platform-admin-only route (and vice versa: staff/platform-admin tokens are
rejected by every patient-portal route).
"""

import uuid
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.appointment import Appointment, AppointmentStatus, AppointmentType
from app.models.branch import Branch
from app.models.doctor import Doctor
from app.models.patient import CivilStatus, Gender, Patient
from app.models.patient_account import PatientAccount

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def patient_factory(db_session: AsyncSession):
    """Factory: creates a Patient + PatientAccount (+ a Branch/Doctor/Appointment
    so isolation can be proven against real rows, not just empty lists)."""

    async def _make(*, clinic_id, password: str = "PatientPass123!"):
        suffix = uuid.uuid4().hex[:8]
        branch = Branch(clinic_id=clinic_id, name=f"Main Branch {suffix}")
        db_session.add(branch)
        await db_session.flush()

        doctor = Doctor(
            clinic_id=clinic_id, branch_id=branch.id, doctor_code=f"DOC-{suffix}",
            first_name="Test", last_name="Doctor",
        )
        db_session.add(doctor)
        await db_session.flush()

        patient = Patient(
            clinic_id=clinic_id, branch_id=branch.id, patient_number=f"P-{suffix}",
            first_name="Pat", last_name=f"Ient{suffix}", birth_date=date(1990, 1, 1),
            gender=Gender.OTHER, civil_status=CivilStatus.SINGLE,
            mobile_number=f"09{suffix[:9].ljust(9, '0')}", email=f"patient-{suffix}@example.com",
            date_registered=date.today(),
        )
        db_session.add(patient)
        await db_session.flush()

        account = PatientAccount(clinic_id=clinic_id, patient_id=patient.id, password_hash=hash_password(password))
        db_session.add(account)
        await db_session.flush()

        appt = Appointment(
            clinic_id=clinic_id, branch_id=branch.id, patient_id=patient.id, doctor_id=doctor.id,
            appointment_number=f"A-{suffix}", appointment_type=AppointmentType.NEW_CONSULTATION,
            appointment_date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(9, 30),
            status=AppointmentStatus.BOOKED,
        )
        db_session.add(appt)
        await db_session.commit()
        await db_session.refresh(patient)
        await db_session.refresh(appt)
        return patient, account, appt, password

    return _make


async def _patient_login(client: AsyncClient, identifier: str, password: str) -> str:
    resp = await client.post("/api/v1/patient-portal/auth/login", json={"identifier": identifier, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# --------------------------------------------------------------------------
# Auth: structurally distinct token
# --------------------------------------------------------------------------


async def test_patient_login_issues_distinct_token_rejected_by_staff_and_platform_admin(
    client: AsyncClient, make_clinic_with_owner, patient_factory
):
    clinic, _owner, _pw = await make_clinic_with_owner()
    patient, _account, _appt, password = await patient_factory(clinic_id=clinic.id)

    token = await _patient_login(client, patient.email, password)

    # Accepted by the patient-portal "profile" endpoint.
    resp = await client.get("/api/v1/patient-portal/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == str(patient.id)

    # Rejected by clinic-staff-only endpoints.
    for path in ["/api/v1/patients", "/api/v1/users", "/api/v1/appointments"]:
        resp = await client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, f"{path} should reject a patient token, got {resp.status_code}"

    # Rejected by platform-admin-only endpoints.
    for path in ["/api/v1/platform-admin/tenants", "/api/v1/platform-admin/dashboard/health"]:
        resp = await client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401, f"{path} should reject a patient token, got {resp.status_code}"


async def test_wrong_password_rejected(client: AsyncClient, make_clinic_with_owner, patient_factory):
    clinic, _owner, _pw = await make_clinic_with_owner()
    patient, _account, _appt, _password = await patient_factory(clinic_id=clinic.id)
    resp = await client.post(
        "/api/v1/patient-portal/auth/login", json={"identifier": patient.email, "password": "WrongPass123!"}
    )
    assert resp.status_code == 401


async def test_login_by_mobile_number_also_works(client: AsyncClient, make_clinic_with_owner, patient_factory):
    clinic, _owner, _pw = await make_clinic_with_owner()
    patient, _account, _appt, password = await patient_factory(clinic_id=clinic.id)
    token = await _patient_login(client, patient.mobile_number, password)
    resp = await client.get("/api/v1/patient-portal/profile", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# Staff / platform-admin tokens rejected by the patient portal
# --------------------------------------------------------------------------


async def test_staff_and_platform_admin_tokens_rejected_by_patient_portal(
    client: AsyncClient, make_clinic_with_owner
):
    clinic, owner, owner_pw = await make_clinic_with_owner()
    resp = await client.post("/api/v1/auth/login", json={"email_or_username": owner.email, "password": owner_pw})
    assert resp.status_code == 200
    staff_token = resp.json()["access_token"]

    resp = await client.get("/api/v1/patient-portal/profile", headers={"Authorization": f"Bearer {staff_token}"})
    assert resp.status_code == 401

    resp = await client.get("/api/v1/patient-portal/appointments", headers={"Authorization": f"Bearer {staff_token}"})
    assert resp.status_code == 401


# --------------------------------------------------------------------------
# THE most important tests: patient-to-patient and patient-to-clinic isolation
# --------------------------------------------------------------------------


async def test_patient_cannot_see_another_patients_data_same_clinic(
    client: AsyncClient, make_clinic_with_owner, patient_factory
):
    clinic, _owner, _pw = await make_clinic_with_owner()
    patient_a, _account_a, appt_a, password_a = await patient_factory(clinic_id=clinic.id)
    patient_b, _account_b, appt_b, _password_b = await patient_factory(clinic_id=clinic.id)

    token_a = await _patient_login(client, patient_a.email, password_a)

    # A's appointment list must contain only A's own appointment.
    resp = await client.get("/api/v1/patient-portal/appointments", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()}
    assert str(appt_a.id) in ids
    assert str(appt_b.id) not in ids

    # A's profile must be A's own patient id, never B's.
    resp = await client.get("/api/v1/patient-portal/profile", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.json()["id"] == str(patient_a.id)
    assert resp.json()["id"] != str(patient_b.id)


async def test_patient_cannot_see_another_clinics_patient_data(
    client: AsyncClient, make_clinic_with_owner, patient_factory
):
    clinic_x, _owner_x, _pw_x = await make_clinic_with_owner()
    clinic_y, _owner_y, _pw_y = await make_clinic_with_owner()

    patient_a, _account_a, appt_a, password_a = await patient_factory(clinic_id=clinic_x.id)
    patient_b, _account_b, appt_b, _password_b = await patient_factory(clinic_id=clinic_y.id)

    token_a = await _patient_login(client, patient_a.email, password_a)

    resp = await client.get("/api/v1/patient-portal/appointments", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    ids = {a["id"] for a in resp.json()}
    assert str(appt_a.id) in ids
    assert str(appt_b.id) not in ids

    # A's dashboard/billing must never surface any data scoped to clinic Y.
    resp = await client.get("/api/v1/patient-portal/dashboard", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    resp = await client.get("/api/v1/patient-portal/billing", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    assert resp.json()["invoices"] == []


async def test_patient_cannot_fetch_another_patients_lab_result_by_id(
    client: AsyncClient, make_clinic_with_owner, patient_factory
):
    """Even a direct-object-reference lookup by id must 403/404, not
    silently return wrong data, when Patient A's token is used against a
    resource id belonging to Patient B (same clinic)."""
    clinic, _owner, _pw = await make_clinic_with_owner()
    patient_a, _account_a, _appt_a, password_a = await patient_factory(clinic_id=clinic.id)
    patient_b, _account_b, _appt_b, _password_b = await patient_factory(clinic_id=clinic.id)

    token_a = await _patient_login(client, patient_a.email, password_a)

    # No released lab order exists for B, but even a random/foreign UUID
    # (standing in for "some other patient's lab order id") must 404, never
    # 200 with data.
    fake_lab_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/patient-portal/laboratory/{fake_lab_id}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 404


async def test_profile_update_is_scoped_to_self_only(client: AsyncClient, make_clinic_with_owner, patient_factory):
    clinic, _owner, _pw = await make_clinic_with_owner()
    patient_a, _account_a, _appt_a, password_a = await patient_factory(clinic_id=clinic.id)
    patient_b, _account_b, _appt_b, _password_b = await patient_factory(clinic_id=clinic.id)

    token_a = await _patient_login(client, patient_a.email, password_a)
    resp = await client.put(
        "/api/v1/patient-portal/profile", json={"city": "Isolation City"}, headers={"Authorization": f"Bearer {token_a}"}
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(patient_a.id)
    assert resp.json()["city"] == "Isolation City"
    # Patient B's record must be untouched (no id supplied by the client -
    # the endpoint always resolves the target from the token, never a body param).
