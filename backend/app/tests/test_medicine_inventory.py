"""Medicine Inventory Phase 1: Medicine catalog + MedicineBatch CRUD,
tenant isolation, quantity/expiry validation, batch status computation, and
role permissions."""

import uuid
from datetime import date, timedelta

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


async def _make_role_login(db_session: AsyncSession, *, clinic_id, role_name: str, password: str):
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


def _medicine_payload(**overrides) -> dict:
    payload = {
        "generic_name": "Paracetamol", "brand_name": "Biogesic", "strength": "500mg",
        "dosage_form": "Tablet", "unit": "tablet", "reorder_level": 50,
    }
    payload.update(overrides)
    return payload


def _batch_payload(**overrides) -> dict:
    payload = {
        "batch_number": "P2026-07-A", "quantity_received": 120, "quantity_remaining": 120,
        "expiry_date": (date.today() + timedelta(days=180)).isoformat(),
        "received_date": date.today().isoformat(), "supplier": "MedSupply Corp", "cost_per_unit": "2.50",
    }
    payload.update(overrides)
    return payload


# --- 1. Medicine creation ---

async def test_create_medicine(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    resp = await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["generic_name"] == "Paracetamol"
    assert body["is_active"] is True


# --- 2. Medicine update ---

async def test_update_medicine(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    created = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    resp = await client.put(f"/api/v1/medicines/{created['id']}", headers=headers, json={"reorder_level": 75, "is_active": False})
    assert resp.status_code == 200, resp.text
    assert resp.json()["reorder_level"] == 75
    assert resp.json()["is_active"] is False


# --- 3. Medicine clinic isolation ---

async def test_medicine_clinic_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    created = (await client.post("/api/v1/medicines", headers=headers_a, json=_medicine_payload())).json()

    resp = await client.get(f"/api/v1/medicines/{created['id']}", headers=headers_b)
    assert resp.status_code == 404, resp.text

    listed_b = await client.get("/api/v1/medicines", headers=headers_b)
    assert all(item["id"] != created["id"] for item in listed_b.json()["items"])


# --- 4. Batch creation ---

async def test_create_batch(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    resp = await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["batch_number"] == "P2026-07-A"
    assert body["status"] == "Active"


# --- 5. Batch cannot reference another clinic's medicine ---

async def test_batch_cannot_reference_another_clinics_medicine(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)

    medicine = (await client.post("/api/v1/medicines", headers=headers_a, json=_medicine_payload())).json()

    resp = await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers_b, json=_batch_payload())
    assert resp.status_code == 404, resp.text


# --- 6. Duplicate batch number within same medicine/clinic rejected ---

async def test_duplicate_batch_number_same_medicine_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    first = await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload())
    assert first.status_code == 201, first.text

    second = await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload())
    assert second.status_code == 409, second.text


# --- 7. Same batch number under a different medicine is allowed ---

async def test_same_batch_number_different_medicine_allowed(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_1 = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    medicine_2 = (
        await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload(generic_name="Amoxicillin", brand_name="Amoxil"))
    ).json()

    first = await client.post(f"/api/v1/medicines/{medicine_1['id']}/batches", headers=headers, json=_batch_payload())
    assert first.status_code == 201, first.text

    second = await client.post(f"/api/v1/medicines/{medicine_2['id']}/batches", headers=headers, json=_batch_payload())
    assert second.status_code == 201, second.text


# --- 8. Negative quantity rejected ---

async def test_negative_quantity_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    resp = await client.post(
        f"/api/v1/medicines/{medicine['id']}/batches", headers=headers,
        json=_batch_payload(quantity_received=-5, quantity_remaining=-5),
    )
    assert resp.status_code == 422, resp.text


# --- 9. quantity_remaining > quantity_received rejected ---

async def test_quantity_remaining_exceeds_received_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    resp = await client.post(
        f"/api/v1/medicines/{medicine['id']}/batches", headers=headers,
        json=_batch_payload(quantity_received=10, quantity_remaining=20),
    )
    assert resp.status_code == 422, resp.text

    # Same rule enforced on update too, merging existing + partial payload.
    created = (
        await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload(batch_number="B1"))
    ).json()
    resp2 = await client.put(
        f"/api/v1/medicines/{medicine['id']}/batches/{created['id']}", headers=headers,
        json={"quantity_remaining": created["quantity_received"] + 1},
    )
    assert resp2.status_code == 422, resp2.text


# --- 10. Medicine with multiple batches returns all batches ---

async def test_medicine_with_multiple_batches_returns_all(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload(batch_number="A"))
    await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload(batch_number="B"))

    resp = await client.get(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers)
    assert resp.status_code == 200, resp.text
    numbers = {b["batch_number"] for b in resp.json()["items"]}
    assert numbers == {"A", "B"}


# --- 11. Batch edit ---

async def test_edit_batch(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    batch = (await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload())).json()

    resp = await client.put(
        f"/api/v1/medicines/{medicine['id']}/batches/{batch['id']}", headers=headers,
        json={"quantity_remaining": 100, "supplier": "New Supplier"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quantity_remaining"] == 100
    assert resp.json()["supplier"] == "New Supplier"


# --- 12. Batch status behavior ---

async def test_batch_status_active_expired_depleted(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()

    active = (
        await client.post(
            f"/api/v1/medicines/{medicine['id']}/batches", headers=headers,
            json=_batch_payload(batch_number="ACT", expiry_date=(date.today() + timedelta(days=90)).isoformat()),
        )
    ).json()
    assert active["status"] == "Active"

    expired = (
        await client.post(
            f"/api/v1/medicines/{medicine['id']}/batches", headers=headers,
            json=_batch_payload(
                batch_number="EXP", expiry_date=(date.today() - timedelta(days=1)).isoformat(),
                quantity_received=50, quantity_remaining=50,
            ),
        )
    ).json()
    assert expired["status"] == "Expired"

    depleted = (
        await client.post(
            f"/api/v1/medicines/{medicine['id']}/batches", headers=headers,
            json=_batch_payload(
                batch_number="DEP", expiry_date=(date.today() + timedelta(days=90)).isoformat(),
                quantity_received=30, quantity_remaining=0,
            ),
        )
    ).json()
    assert depleted["status"] == "Depleted"

    # Manual Recalled override sticks and is not overwritten by recompute.
    recalled = await client.put(
        f"/api/v1/medicines/{medicine['id']}/batches/{active['id']}", headers=headers, json={"status": "Recalled"}
    )
    assert recalled.status_code == 200, recalled.text
    assert recalled.json()["status"] == "Recalled"

    refetched = await client.get(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers)
    still_recalled = next(b for b in refetched.json()["items"] if b["id"] == active["id"])
    assert still_recalled["status"] == "Recalled"

    # A client cannot set any other explicit status directly.
    bad = await client.put(
        f"/api/v1/medicines/{medicine['id']}/batches/{expired['id']}", headers=headers, json={"status": "Active"}
    )
    assert bad.status_code == 422, bad.text


# --- 13. Role permissions ---

async def test_doctor_can_view_but_not_manage(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=owner_headers, json=_medicine_payload())).json()

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", password="DoctorPass123!")
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    view_resp = await client.get("/api/v1/medicines", headers=doc_headers)
    assert view_resp.status_code == 200, view_resp.text

    create_resp = await client.post("/api/v1/medicines", headers=doc_headers, json=_medicine_payload(generic_name="Ibuprofen"))
    assert create_resp.status_code == 403, create_resp.text

    batch_resp = await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=doc_headers, json=_batch_payload())
    assert batch_resp.status_code == 403, batch_resp.text


async def test_receptionist_can_manage_inventory(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, _headers = await _owner_headers(client, make_clinic_with_owner)

    rec_email, _rec_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist", password="RecPass123!")
    rec_token = await _login(client, rec_email, "RecPass123!")
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    resp = await client.post("/api/v1/medicines", headers=rec_headers, json=_medicine_payload())
    assert resp.status_code == 201, resp.text


async def test_cashier_cannot_view_inventory(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    """Cashier is not in INVENTORY_VIEW_ROLES per the client's explicit role
    spec (only Owner/Administrator/Receptionist/Doctor/Nurse)."""
    clinic, _owner, _headers = await _owner_headers(client, make_clinic_with_owner)

    cashier_email, _cashier_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Cashier", password="CashPass123!")
    cashier_token = await _login(client, cashier_email, "CashPass123!")
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    resp = await client.get("/api/v1/medicines", headers=cashier_headers)
    assert resp.status_code == 403, resp.text


# --- 14. Soft delete/active behavior ---

async def test_medicine_soft_delete_excluded_from_list(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    created = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()

    delete_resp = await client.delete(f"/api/v1/medicines/{created['id']}", headers=headers)
    assert delete_resp.status_code == 204, delete_resp.text

    listed = await client.get("/api/v1/medicines", headers=headers)
    assert all(item["id"] != created["id"] for item in listed.json()["items"])

    # Matches this codebase's existing soft-delete convention (e.g.
    # ClinicServiceCatalogService): `get_by_id_and_clinic` does not filter
    # `is_deleted` (needed so a restore flow can still look the row up by
    # id) - only list/search excludes soft-deleted rows.
    get_resp = await client.get(f"/api/v1/medicines/{created['id']}", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
