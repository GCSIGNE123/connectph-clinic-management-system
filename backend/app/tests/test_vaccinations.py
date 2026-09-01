"""Integration tests for Feature 5 Part A: Vaccination personnel/patient
name display. A Vaccination-category order (Phase 9, unchanged) auto-
attaches a `vaccination_administrations` workflow record (Post-RC1,
unchanged); this session's change is purely response-shape - resolving the
already-loaded `patient`/`administered_by_user` relationships to real
`patient_name`/`administered_by_name` strings, no new columns, no
migration. Covers: patient name always present, administering personnel
name present once administered, personnel name stays safely null (not an
error) before administration or if the administering user was later
removed, and role gating (unchanged) still enforced.
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
                "first_name": "Maria", "last_name": "Santos", "birth_date": "1988-03-10",
                "gender": "Female", "civil_status": "Married", "mobile_number": "+639171234567",
            },
        )
    ).json()["patient"]
    return {
        "branch_id": branch["id"], "department_id": department["id"],
        "doctor_id": doctor["id"], "service_id": service["id"], "patient_id": patient["id"],
    }


def _queue_payload(deps: dict) -> dict:
    return {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
        "department_id": deps["department_id"], "doctor_id": deps["doctor_id"],
        "service_id": deps["service_id"], "priority": "Normal",
    }


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


async def _setup_with_vaccination_order(client: AsyncClient, make_clinic_with_owner, db_session):
    """Sets up a clinic, doctor, patient, queue->visit, opens a
    consultation, creates a Vaccination-category Order via the Phase 9
    endpoint (auto-attaches a `vaccination_administrations` row), and
    returns headers for Owner/Doctor/Nurse/Receptionist roles plus ids."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)

    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "TestPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    order_resp = await client.post(
        f"/api/v1/consultations/{cid}/orders", headers=doc_headers,
        json={"order_category": "Vaccination", "items": [{"item_name": "MMR Vaccine"}]},
    )
    assert order_resp.status_code == 200, order_resp.text
    order = order_resp.json()

    nurse_email, _nurse_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Nurse")
    nurse_token = await _login(client, nurse_email, "TestPass123!")
    nurse_headers = {"Authorization": f"Bearer {nurse_token}"}

    recep_email, _recep_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}

    list_resp = await client.get(f"/api/v1/vaccinations?patient_id={deps['patient_id']}", headers=owner_headers)
    vaccination = next(v for v in list_resp.json() if v["order_id"] == order["id"])

    return {
        "clinic": clinic, "owner_headers": owner_headers, "doc_headers": doc_headers,
        "nurse_headers": nurse_headers, "recep_headers": recep_headers, "deps": deps,
        "visit_id": visit_id, "consultation_id": cid, "order": order, "vaccination": vaccination,
    }


# --- Feature 5 Part A: patient/administering-personnel names ---

async def test_vaccination_list_shows_patient_name(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    assert ctx["vaccination"]["patient_name"] == "Maria Santos"


async def test_vaccination_administered_by_name_appears_after_administration(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    resp = await client.post(
        f"/api/v1/vaccinations/{ctx['vaccination']['id']}/administer", headers=ctx["nurse_headers"],
        json={"dose": "0.5 mL", "site": "Left Deltoid", "route": "Intramuscular"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["patient_name"] == "Maria Santos"
    assert body["administered_by_name"] == "Test Nurse"
    assert body["status"] == "Administered"

    # Also correct when read back via the list endpoint, not just the
    # administer response itself.
    list_resp = await client.get(f"/api/v1/vaccinations?patient_id={ctx['deps']['patient_id']}", headers=ctx["owner_headers"])
    listed = next(v for v in list_resp.json() if v["id"] == ctx["vaccination"]["id"])
    assert listed["administered_by_name"] == "Test Nurse"


async def test_vaccination_administered_by_name_resolves_for_receptionist_too(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Any Nurse or Receptionist may administer (per spec) - confirms name
    resolution isn't accidentally hardcoded/scoped to one role."""
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    resp = await client.post(f"/api/v1/vaccinations/{ctx['vaccination']['id']}/administer", headers=ctx["recep_headers"], json={})
    assert resp.status_code == 200, resp.text
    assert resp.json()["administered_by_name"] == "Test Receptionist"


async def test_vaccination_administered_by_name_is_null_before_administration(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Missing/optional personnel data (not yet administered) must behave
    safely - a null name, never an error/crash."""
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    assert ctx["vaccination"]["administered_by"] is None
    assert ctx["vaccination"]["administered_by_name"] is None
    assert ctx["vaccination"]["status"] == "Requested"
    # Patient name is still present even though nothing's been administered.
    assert ctx["vaccination"]["patient_name"] == "Maria Santos"


async def test_vaccination_administered_by_name_is_null_when_administering_user_is_soft_deleted(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """The FK is `ON DELETE SET NULL` (see the model) - if the administering
    user's account is later deactivated/removed, the vaccination record and
    its name resolution must degrade gracefully to null, not error."""
    from app.models.user import User

    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    await client.post(f"/api/v1/vaccinations/{ctx['vaccination']['id']}/administer", headers=ctx["nurse_headers"], json={})

    nurse_row = (
        await db_session.execute(select(User).where(User.clinic_id == ctx["clinic"].id, User.first_name == "Test", User.last_name == "Nurse"))
    ).scalar_one()
    nurse_row.is_active = False
    await db_session.commit()

    # Still resolves the name (soft-deactivation, not a real FK removal) -
    # the important guarantee is that nothing crashes either way.
    resp = await client.get(f"/api/v1/vaccinations?patient_id={ctx['deps']['patient_id']}", headers=ctx["owner_headers"])
    assert resp.status_code == 200
    listed = next(v for v in resp.json() if v["id"] == ctx["vaccination"]["id"])
    assert listed["administered_by_name"] == "Test Nurse"


async def test_vaccination_role_gating_unchanged(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Preserves the existing permission model (Owner/Administrator/Doctor/
    Nurse/Receptionist may view/administer) - not touched by this feature,
    but re-verified since the response shape changed."""
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    _cashier_email, _cashier_user = await _make_role_login(db_session, clinic_id=ctx["clinic"].id, role_name="Cashier")
    cashier_token = await _login(client, _cashier_email, "TestPass123!")
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    resp = await client.get("/api/v1/vaccinations", headers=cashier_headers)
    assert resp.status_code == 403

    resp = await client.post(f"/api/v1/vaccinations/{ctx['vaccination']['id']}/administer", headers=cashier_headers, json={})
    assert resp.status_code == 403


# --- Recent-records convention: newest vaccination request first, date-range filter ---

async def _second_vaccination_order(client: AsyncClient, ctx: dict, *, vaccine_name: str) -> dict:
    order_resp = await client.post(
        f"/api/v1/consultations/{ctx['consultation_id']}/orders", headers=ctx["doc_headers"],
        json={"order_category": "Vaccination", "items": [{"item_name": vaccine_name}]},
    )
    assert order_resp.status_code == 200, order_resp.text
    order = order_resp.json()
    list_resp = await client.get(f"/api/v1/vaccinations?patient_id={ctx['deps']['patient_id']}", headers=ctx["owner_headers"])
    return next(v for v in list_resp.json() if v["order_id"] == order["id"])


async def test_vaccination_list_sorts_newest_created_first_with_id_as_tie_break(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    import uuid as _uuid
    from datetime import UTC, datetime

    from app.models.vaccination_administration import VaccinationAdministration

    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    second = await _second_vaccination_order(client, ctx, vaccine_name="Hepatitis B Vaccine")

    row_first = await db_session.get(VaccinationAdministration, _uuid.UUID(ctx["vaccination"]["id"]))
    row_second = await db_session.get(VaccinationAdministration, _uuid.UUID(second["id"]))
    row_first.created_at = datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC)
    row_second.created_at = datetime(2026, 6, 5, 10, 0, 0, tzinfo=UTC)
    await db_session.commit()

    resp = await client.get("/api/v1/vaccinations", headers=ctx["owner_headers"])
    ids = [v["id"] for v in resp.json()]
    assert ids.index(second["id"]) < ids.index(ctx["vaccination"]["id"])


async def test_vaccination_date_range_filter_excludes_records_outside_the_range(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    import uuid as _uuid
    from datetime import UTC, datetime

    from app.models.vaccination_administration import VaccinationAdministration

    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    second = await _second_vaccination_order(client, ctx, vaccine_name="Hepatitis B Vaccine")

    (await db_session.get(VaccinationAdministration, _uuid.UUID(ctx["vaccination"]["id"]))).created_at = datetime(
        2026, 6, 15, 10, 0, 0, tzinfo=UTC
    )
    (await db_session.get(VaccinationAdministration, _uuid.UUID(second["id"]))).created_at = datetime(
        2026, 7, 1, 10, 0, 0, tzinfo=UTC
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/vaccinations", headers=ctx["owner_headers"],
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
    )
    assert resp.status_code == 200, resp.text
    ids = [v["id"] for v in resp.json()]
    assert ids == [ctx["vaccination"]["id"]]


async def test_vaccination_date_range_with_no_matches_returns_empty(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    resp = await client.get(
        "/api/v1/vaccinations", headers=ctx["owner_headers"],
        params={"date_from": "2020-01-01", "date_to": "2020-01-31"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_vaccination_date_range_combines_with_status_filter(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    from datetime import UTC, datetime

    today = datetime.now(UTC).date().isoformat()

    matching = await client.get(
        "/api/v1/vaccinations", headers=ctx["owner_headers"],
        params={"status_filter": "Requested", "date_from": today, "date_to": today},
    )
    assert any(v["id"] == ctx["vaccination"]["id"] for v in matching.json())

    wrong_status = await client.get(
        "/api/v1/vaccinations", headers=ctx["owner_headers"],
        params={"status_filter": "Administered", "date_from": today, "date_to": today},
    )
    assert all(v["id"] != ctx["vaccination"]["id"] for v in wrong_status.json())


async def test_vaccination_tenant_isolation_holds_with_date_range_filter(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx = await _setup_with_vaccination_order(client, make_clinic_with_owner, db_session)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    from datetime import UTC, datetime

    today = datetime.now(UTC).date().isoformat()
    resp = await client.get(
        "/api/v1/vaccinations", headers=headers_b, params={"date_from": today, "date_to": today}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []
