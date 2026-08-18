"""Walk-in laboratory queue tickets: a Reception queue ticket created
directly for a "Laboratory"-named department, with no doctor assigned, has
no consultation/Order to place a lab order through - previously this meant
it could NEVER reach the Laboratory role's worklist, even though the
queue-print vitals-exemption logic already anticipated "a walk-in lab
order" as a real scenario. `QueueService.create_queue` now auto-creates a
LaboratoryOrder for such tickets via `LaboratoryService.
create_from_queue_ticket` - see that method and its call site for the full
reasoning, including why the match is on the department's NAME rather than
`department_code == "LAB"` (a real clinic's Laboratory department was
found coded "D03", not the seeded default's "LAB")."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.laboratory_order import LaboratoryOrder
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
            json={"service_code": "CBC1", "service_name": "CBC, PLATELET", "default_price": "250.00"},
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


async def test_walk_in_laboratory_queue_ticket_creates_lab_order_even_with_custom_department_code(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession
) -> None:
    """The exact real-world case this fix targets: a clinic's Laboratory
    department is named "Laboratory" but coded something other than the
    seeded default "LAB" (observed live as "D03") - the auto-created
    LaboratoryOrder must not depend on that code."""
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="D03", department_name="Laboratory")

    queue_resp = await client.post(
        "/api/v1/queues", headers=owner_headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
            "doctor_id": None, "service_id": deps["service_id"], "priority": "Normal",
        },
    )
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


async def test_walk_in_lab_order_created_even_with_no_matching_template(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """No Laboratory templates configured at all is a real, observed
    clinic state - the order must still be created (unlinked, template_id
    None), not silently skipped, or the worklist stays empty exactly like
    the original bug report."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="D03")

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
    orders = orders_resp.json()
    assert len(orders) == 1
    assert orders[0]["template_id"] is None
    assert orders[0]["test_type"] == "CBC, PLATELET"


async def test_queue_ticket_with_doctor_assigned_does_not_auto_create_lab_order(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """A doctor-assigned queue ticket (Consultation/Follow-up-style) is not
    a walk-in - it must go through the normal doctor-placed-order flow
    (`create_from_order`), not have this auto-creation fire alongside it
    just because the selected service happens to share a name with a lab
    test."""
    _clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup(client, owner_headers, department_code="D03")
    doctor = (await client.post("/api/v1/doctors", headers=owner_headers, json={"first_name": "Jose", "last_name": "Rizal"})).json()

    queue_resp = await client.post(
        "/api/v1/queues", headers=owner_headers,
        json={
            "patient_id": deps["patient_id"], "branch_id": deps["branch_id"], "department_id": deps["department_id"],
            "doctor_id": doctor["id"], "service_id": deps["service_id"], "priority": "Normal",
        },
    )
    assert queue_resp.status_code == 201, queue_resp.text
    queue = queue_resp.json()

    orders_resp = await client.get(f"/api/v1/laboratory/orders?visit_id={queue['visit_id']}", headers=owner_headers)
    assert orders_resp.json() == []


async def test_non_laboratory_department_walk_in_queue_does_not_create_lab_order(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    """A walk-in ticket for an unrelated department (e.g. Radiology) whose
    service name doesn't happen to be named after a department called
    "Laboratory" must not create a lab order."""
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
