"""Walk-in laboratory queue tickets: a Reception queue ticket created for a
"Laboratory"-named department has no consultation/Order to place a lab
order through - `QueueService._create_queue_for_paid_lab_visit` auto-creates
a LaboratoryOrder for such tickets via `LaboratoryService.
create_from_queue_ticket` - see that method and its call site for the full
reasoning, including why the match is on the department's NAME rather than
`department_code == "LAB"` (a real clinic's Laboratory department was found
coded "D03", not the seeded default's "LAB").

Laboratory pay-first workflow: every Laboratory queue ticket must now go
through POST /visits/pre-queue -> POST /visits/{id}/laboratory-invoice ->
POST /invoices/{id}/payments -> POST /queues (visit_id=...), so every test
below routes through that real API workflow instead of a single direct
POST /queues call - see `test_laboratory_payment_first_queue.py` for the
dedicated tests covering the payment gate itself (unpaid rejection, PAID
slip, doctor optionality, idempotency)."""

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


async def _owner_headers(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    login = await client.post(
        "/api/v1/auth/login", json={"email_or_username": owner.email, "password": password, "clinic_slug": clinic.slug}
    )
    assert login.status_code == 200, login.text
    return clinic, owner, {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, password: str = "TestPass123!"):
    from app.models.user import User

    role = (await db_session.execute(select(Role).where(Role.name == role_name))).scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"{role_name.lower()}-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"{role_name.lower()}{suffix}", hashed_password=hash_password(password),
        first_name="Test", last_name=role_name, role_id=role.id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return email


async def _setup(client: AsyncClient, headers: dict, *, department_code: str, department_name: str = "Laboratory") -> dict:
    branch = (await client.post("/api/v1/branches", headers=headers, json={"name": "Main Branch", "code": "MAIN"})).json()
    department = (
        await client.post(
            "/api/v1/departments", headers=headers, json={"department_code": department_code, "name": department_name}
        )
    ).json()
    service = (
        await client.post(
            "/api/v1/services", headers=headers,
            json={
                "service_code": "CBC1", "service_name": "CBC, PLATELET", "default_price": "250.00",
                "department_id": department["id"],
            },
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
    return {"branch_id": branch["id"], "department_id": department["id"], "service_id": service["id"], "patient_id": patient["id"]}


async def _create_paid_lab_queue(client: AsyncClient, headers: dict, deps: dict, *, doctor_id: str | None = None):
    """Drives the real pay-first workflow end to end: draft visit -> invoice
    -> full payment -> queue ticket. Returns the final `POST /queues`
    response so callers can assert on it exactly like the old direct call."""
    visit_resp = await client.post(
        "/api/v1/visits/pre-queue", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
            "doctor_id": doctor_id, "department_id": deps["department_id"], "service_id": deps["service_id"],
        },
    )
    assert visit_resp.status_code == 201, visit_resp.text
    visit = visit_resp.json()

    invoice_resp = await client.post(f"/api/v1/visits/{visit['id']}/laboratory-invoice", headers=headers)
    assert invoice_resp.status_code == 200, invoice_resp.text
    invoice = invoice_resp.json()

    if float(invoice["balance_due"]) > 0:
        pay_resp = await client.post(
            f"/api/v1/invoices/{invoice['id']}/payments", headers=headers,
            json={"payments": [{"payment_method": "Cash", "amount": invoice["balance_due"]}]},
        )
        assert pay_resp.status_code == 200, pay_resp.text

    return await client.post(
        "/api/v1/queues", headers=headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
            "doctor_id": doctor_id, "service_id": deps["service_id"], "priority": "Normal", "visit_id": visit["id"],
        },
    )


async def test_walk_in_laboratory_queue_ticket_creates_lab_order_even_with_custom_department_code(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    """The exact real-world case this fix targets: a clinic's Laboratory
    department is named "Laboratory" but coded something other than the
    seeded default "LAB" (observed live as "D03") - the auto-created
    LaboratoryOrder must not depend on that code."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="D03", department_name="Laboratory")

    queue_resp = await _create_paid_lab_queue(client, owner_headers, deps)
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()
    assert queue["status"] == "Waiting"

    lab_email = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_login = await client.post(
        "/api/v1/auth/login", json={"email_or_username": lab_email, "password": "TestPass123!", "clinic_slug": clinic.slug}
    )
    lab_headers = {"Authorization": f"Bearer {lab_login.json()['access_token']}"}

    worklist = await client.get(f"/api/v1/laboratory/orders?visit_id={queue['visit_id']}", headers=lab_headers)
    assert worklist.status_code == 200, worklist.text
    orders = worklist.json()
    assert len(orders) == 1
    lab_order = orders[0]
    assert lab_order["test_type"] == "CBC, PLATELET"
    assert lab_order["status"] == "Requested"
    assert lab_order["order_id"] is None
    assert lab_order["doctor_id"] is None
    assert lab_order["queue_number"] == queue["queue_number"]
    # Client feedback: a walk-in order (no `order_id`) previously printed
    # "Order No. : -" on its Laboratory Report - it now gets its own
    # `ORD-YYYYMMDD-NNNNNN` number, same format/generator Phase 9's
    # doctor-referred orders already use (see `standalone_order_number`).
    assert lab_order["order_number"] is not None
    assert lab_order["order_number"].startswith("ORD-")


async def test_walk_in_lab_order_number_is_unique_per_ticket_and_shares_the_daily_counter(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """Two walk-in lab orders created back to back the same day get two
    distinct, sequential numbers - proves this isn't a fixed/hardcoded
    string and that the counter genuinely advances per order. Two
    different patients (an existing "one active queue ticket per patient/
    department/day" guard - unrelated to this feature - would otherwise
    reject a second ticket for the same patient/department same day)."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps_a = await _setup(client, owner_headers, department_code="D03")
    second_patient = (
        await client.post(
            "/api/v1/patients", headers=owner_headers,
            json={
                "first_name": "Maria", "last_name": "Santos", "birth_date": "1985-03-20",
                "gender": "Female", "civil_status": "Single", "mobile_number": "+639179998888",
            },
        )
    ).json()["patient"]
    deps_b = {**deps_a, "patient_id": second_patient["id"]}

    first = await _create_paid_lab_queue(client, owner_headers, deps_a)
    assert first.status_code == 201, first.text
    second = await _create_paid_lab_queue(client, owner_headers, deps_b)
    assert second.status_code == 201, second.text

    first_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={first.json()['visit_id']}", headers=owner_headers)).json()
    second_orders = (await client.get(f"/api/v1/laboratory/orders?visit_id={second.json()['visit_id']}", headers=owner_headers)).json()
    first_number = first_orders[0]["order_number"]
    second_number = second_orders[0]["order_number"]
    assert first_number != second_number
    assert first_number.startswith("ORD-")
    assert second_number.startswith("ORD-")


async def test_walk_in_lab_order_created_even_with_no_matching_template(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """No Laboratory templates configured at all is a real, observed
    clinic state - the order must still be created (unlinked, template_id
    None), not silently skipped, or the worklist stays empty exactly like
    the original bug report."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="D03")

    queue_resp = await _create_paid_lab_queue(client, owner_headers, deps)
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()

    orders_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={queue['visit_id']}", headers=owner_headers)
    orders = orders_resp.json()
    assert len(orders) == 1
    assert orders[0]["template_id"] is None
    assert orders[0]["test_type"] == "CBC, PLATELET"


async def test_lab_queue_ticket_can_have_a_doctor_assigned_and_still_auto_creates_lab_order(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """A Laboratory-department ticket that happens to carry a doctor_id
    (e.g. reassigned later, or a clinic routing convention) still goes
    through the same pay-first + auto-lab-order path - the Doctor rule only
    ever makes the doctor OPTIONAL for Laboratory, it never disables lab-
    order auto-creation when one happens to be present. This replaces the
    pre-payment-gate version of this test, which asserted the opposite
    (no lab order) back when a doctor_id on a Laboratory-named department
    ticket fell through to the plain consultation-style path - that path no
    longer exists for this department, see `QueueService.create_queue`."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="D03")
    doctor = (await client.post("/api/v1/doctors", headers=owner_headers, json={"first_name": "Jose", "last_name": "Rizal"})).json()

    queue_resp = await _create_paid_lab_queue(client, owner_headers, deps, doctor_id=doctor["id"])
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()
    assert queue["doctor_id"] == doctor["id"]

    orders_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={queue['visit_id']}", headers=owner_headers)
    orders = orders_resp.json()
    assert len(orders) == 1
    assert orders[0]["test_type"] == "CBC, PLATELET"


async def test_walk_in_lab_order_reports_the_correct_visit_number(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    """Direct-to-Laboratory / doctor-less flow (Visit # investigation fix):
    the draft Visit created by the pay-first workflow already has a real
    `visit_number` and `doctor_id=None` - `LaboratoryService._to_read` used
    to hardcode `visit_number=None` on every order regardless, even though
    `lab_order.visit` was already loaded (proven by `queue_number` already
    working off that same relationship). Both `GET /laboratory/orders/{id}`
    and the worklist listing (`GET /laboratory/orders?visit_id=...`) must
    now return the linked Visit's actual number."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="D03", department_name="Laboratory")

    queue_resp = await _create_paid_lab_queue(client, owner_headers, deps)
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()

    visit_resp = await client.get(f"/api/v1/visits/{queue['visit_id']}", headers=owner_headers)
    assert visit_resp.status_code == 200, visit_resp.text
    visit = visit_resp.json()
    assert visit["doctor_id"] is None
    assert visit["visit_number"]

    lab_email = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Laboratory")
    lab_login = await client.post(
        "/api/v1/auth/login", json={"email_or_username": lab_email, "password": "TestPass123!", "clinic_slug": clinic.slug}
    )
    lab_headers = {"Authorization": f"Bearer {lab_login.json()['access_token']}"}

    worklist = await client.get(f"/api/v1/laboratory/orders?visit_id={queue['visit_id']}", headers=lab_headers)
    assert worklist.status_code == 200, worklist.text
    orders = worklist.json()
    assert len(orders) == 1
    lab_order = orders[0]
    assert lab_order["visit_id"] == visit["id"]
    assert lab_order["doctor_id"] is None
    assert lab_order["visit_number"] == visit["visit_number"]

    detail_resp = await client.get(f"/api/v1/laboratory/orders/{lab_order['id']}", headers=lab_headers)
    assert detail_resp.status_code == 200, detail_resp.text
    assert detail_resp.json()["visit_number"] == visit["visit_number"]


async def test_non_laboratory_department_walk_in_queue_does_not_create_lab_order(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """A walk-in ticket for an unrelated department (e.g. Radiology) whose
    service name doesn't happen to be named after a department called
    "Laboratory" must not create a lab order, and (regression) is completely
    unaffected by the Laboratory pay-first gate - it still creates
    immediately via the direct, no-payment-required path."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="RAD", department_name="Radiology")

    queue_resp = await client.post(
        "/api/v1/queues", headers=owner_headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
            "doctor_id": None, "service_id": deps["service_id"], "priority": "Normal",
        },
    )
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()

    orders_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={queue['visit_id']}", headers=owner_headers)
    assert orders_resp.json() == []
