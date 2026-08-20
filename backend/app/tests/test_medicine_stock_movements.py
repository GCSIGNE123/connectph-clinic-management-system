"""Medicine Inventory Phase 2: MedicineStockMovement ledger - movement
validation, quantity/status accounting, audit events, concurrency, clinic
isolation, role permissions, and Phase 1 compatibility."""

import asyncio
import uuid
from datetime import date, timedelta

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
        "batch_number": "P2026-07-A", "quantity_received": 100, "quantity_remaining": 100,
        "expiry_date": (date.today() + timedelta(days=180)).isoformat(),
        "received_date": date.today().isoformat(), "supplier": "MedSupply Corp", "cost_per_unit": "2.50",
    }
    payload.update(overrides)
    return payload


async def _create_medicine_and_batch(client: AsyncClient, headers: dict, **batch_overrides) -> tuple[str, str]:
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    batch = (
        await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload(**batch_overrides))
    ).json()
    return medicine["id"], batch["id"]


def _movements_url(medicine_id: str, batch_id: str) -> str:
    return f"/api/v1/medicines/{medicine_id}/batches/{batch_id}/movements"


# --- 1. Receive stock increases quantity ---

async def test_received_movement_increases_quantity(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Received", "quantity_delta": 50, "reason": "Restock PO-1001"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["quantity_delta"] == 50
    assert body["resulting_quantity"] == 150

    batch = (await client.get(f"/api/v1/medicines/{medicine_id}/batches", headers=headers)).json()["items"][0]
    assert batch["quantity_remaining"] == 150
    assert batch["quantity_received"] == 150  # cap raised by the same amount


# --- 2. Adjustment decreases quantity ---

async def test_adjustment_movement_decreases_quantity(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": -5, "reason": "Damaged units"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["resulting_quantity"] == 95


# --- 3. Adjustment can increase quantity when valid ---

async def test_adjustment_movement_can_increase_quantity(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers, quantity_received=100, quantity_remaining=80)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": 15, "reason": "Recount correction"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["resulting_quantity"] == 95

    # But not beyond the received cap.
    over_cap = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": 10, "reason": "Recount correction 2"},
    )
    assert over_cap.status_code == 422, over_cap.text


# --- 4. Negative stock prevented ---

async def test_negative_stock_prevented(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers, quantity_received=10, quantity_remaining=10)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": -20, "reason": "Too much"},
    )
    assert resp.status_code == 422, resp.text

    batch = (await client.get(f"/api/v1/medicines/{medicine_id}/batches", headers=headers)).json()["items"][0]
    assert batch["quantity_remaining"] == 10  # unchanged


# --- 5. Invalid positive/negative movement types rejected ---

async def test_invalid_sign_for_movement_type_rejected(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    negative_received = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Received", "quantity_delta": -10, "reason": "bad"},
    )
    assert negative_received.status_code == 422, negative_received.text

    positive_dispensed = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Dispensed", "quantity_delta": 5},
    )
    assert positive_dispensed.status_code == 422, positive_dispensed.text

    positive_expired = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Expired", "quantity_delta": 5, "reason": "bad"},
    )
    assert positive_expired.status_code == 422, positive_expired.text

    positive_recalled = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Recalled", "quantity_delta": 5, "reason": "bad"},
    )
    assert positive_recalled.status_code == 422, positive_recalled.text

    zero_delta = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": 0, "reason": "bad"},
    )
    assert zero_delta.status_code == 422, zero_delta.text


# --- 6. Adjustment requires reason ---

async def test_adjustment_requires_reason(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": -5},
    )
    assert resp.status_code == 422, resp.text


# --- 7. Expired movement decreases quantity ---

async def test_expired_movement_decreases_quantity(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Expired", "quantity_delta": -100, "reason": "Past expiry, pulled from shelf"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["resulting_quantity"] == 0

    # Expired requires a reason too, consistent with Adjustment/Recalled.
    resp_no_reason = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers, json={"movement_type": "Expired", "quantity_delta": -1}
    )
    assert resp_no_reason.status_code == 422, resp_no_reason.text


# --- 8. Recalled movement decreases quantity ---

async def test_recalled_movement_decreases_quantity_and_sets_status(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Recalled", "quantity_delta": -30, "reason": "Manufacturer recall #RC-5"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["resulting_quantity"] == 70

    batch = (await client.get(f"/api/v1/medicines/{medicine_id}/batches", headers=headers)).json()["items"][0]
    assert batch["status"] == "Recalled"  # explicit override, preserved as a historical record


# --- 9. Depleted status is updated appropriately ---

async def test_depleted_status_after_quantity_reaches_zero(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers, quantity_received=20, quantity_remaining=20)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Dispensed", "quantity_delta": -20},
    )
    assert resp.status_code == 201, resp.text

    batch = (await client.get(f"/api/v1/medicines/{medicine_id}/batches", headers=headers)).json()["items"][0]
    assert batch["quantity_remaining"] == 0
    assert batch["status"] == "Depleted"


# --- 10. Movement ledger records resulting quantity ---

async def test_movement_records_resulting_quantity_sequence(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers, quantity_received=100, quantity_remaining=100)

    await client.post(_movements_url(medicine_id, batch_id), headers=headers, json={"movement_type": "Adjustment", "quantity_delta": -5, "reason": "a"})
    await client.post(_movements_url(medicine_id, batch_id), headers=headers, json={"movement_type": "Received", "quantity_delta": 20, "reason": "b"})

    listed = await client.get(_movements_url(medicine_id, batch_id), headers=headers)
    resulting = [m["resulting_quantity"] for m in listed.json()["items"]]
    # Newest first (reverse chronological): Received(20) applied after Adjustment(-5).
    assert resulting == [115, 95]


# --- 11. Audit event created ---

async def test_audit_event_created_for_movement(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    from app.models.audit_log import AuditLog

    clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": -5, "reason": "Damaged units"},
    )
    assert resp.status_code == 201, resp.text

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.action == "inventory.stock_movement", AuditLog.clinic_id == clinic.id)
    )
    entries = result.scalars().all()
    assert len(entries) == 1
    assert entries[0].metadata_json["movement_type"] == "Adjustment"
    assert entries[0].metadata_json["quantity_delta"] == -5
    assert entries[0].metadata_json["resulting_quantity"] == 95


# --- 12. Clinic isolation ---

async def test_movement_clinic_isolation(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic_a, _owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers_a)

    read_other = await client.get(_movements_url(medicine_id, batch_id), headers=headers_b)
    assert read_other.status_code == 404, read_other.text

    create_other = await client.post(
        _movements_url(medicine_id, batch_id), headers=headers_b,
        json={"movement_type": "Adjustment", "quantity_delta": -1, "reason": "hostile"},
    )
    assert create_other.status_code == 404, create_other.text

    # Clinic A's batch quantity must be untouched by clinic B's attempt.
    batch = (await client.get(f"/api/v1/medicines/{medicine_id}/batches", headers=headers_a)).json()["items"][0]
    assert batch["quantity_remaining"] == 100


# --- 13. Role permissions ---

async def test_doctor_can_view_but_not_create_movements(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, owner_headers)

    doc_email, _doc_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", password="DoctorPass123!")
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}

    view_resp = await client.get(_movements_url(medicine_id, batch_id), headers=doc_headers)
    assert view_resp.status_code == 200, view_resp.text

    create_resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=doc_headers,
        json={"movement_type": "Adjustment", "quantity_delta": -1, "reason": "nope"},
    )
    assert create_resp.status_code == 403, create_resp.text


async def test_receptionist_can_create_movements(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, owner_headers)

    rec_email, _rec_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist", password="RecPass123!")
    rec_token = await _login(client, rec_email, "RecPass123!")
    rec_headers = {"Authorization": f"Bearer {rec_token}"}

    resp = await client.post(
        _movements_url(medicine_id, batch_id), headers=rec_headers,
        json={"movement_type": "Received", "quantity_delta": 10, "reason": "Restock"},
    )
    assert resp.status_code == 201, resp.text


async def test_cashier_cannot_view_movements(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, owner_headers)

    cashier_email, _cashier_user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Cashier", password="CashPass123!")
    cashier_token = await _login(client, cashier_email, "CashPass123!")
    cashier_headers = {"Authorization": f"Bearer {cashier_token}"}

    resp = await client.get(_movements_url(medicine_id, batch_id), headers=cashier_headers)
    assert resp.status_code == 403, resp.text


# --- 14. Batch/medicine relationship validation ---

async def test_movement_rejected_when_batch_does_not_belong_to_medicine(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id_1, batch_id_1 = await _create_medicine_and_batch(client, headers, batch_number="M1-BATCH")
    medicine_id_2, _batch_id_2 = await _create_medicine_and_batch(client, headers, batch_number="M2-BATCH")

    # batch_id_1 actually belongs to medicine_id_1, not medicine_id_2.
    resp = await client.post(
        _movements_url(medicine_id_2, batch_id_1), headers=headers,
        json={"movement_type": "Adjustment", "quantity_delta": -1, "reason": "mismatch"},
    )
    assert resp.status_code == 404, resp.text


# --- 15. Transaction rollback if movement insertion or quantity update fails ---

async def test_rollback_on_failure_leaves_quantity_and_ledger_unchanged(
    client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession, monkeypatch
) -> None:
    """Exercises the real service directly (rather than through HTTP, which
    would just propagate the exception through the ASGI test transport
    rather than yielding a clean response) - same approach as
    `test_services_catalog.py`'s own forced-failure regression test."""
    from app.schemas.medicine import MedicineBatchCreate, MedicineCreate, MedicineStockMovementCreate
    from app.services.medicine_service import MedicineService

    clinic, owner, _password = await make_clinic_with_owner()
    service = MedicineService(db_session)
    medicine = await service.create(MedicineCreate(**_medicine_payload()), clinic_id=clinic.id, actor=owner)
    batch = await service.create_batch(
        medicine.id, MedicineBatchCreate(**_batch_payload()), clinic_id=clinic.id, actor=owner
    )
    # Captured before rollback() expires every instance in this session -
    # subsequent lookups use these plain UUIDs, never a possibly-expired
    # ORM attribute.
    medicine_id, batch_id, clinic_id = medicine.id, batch.id, clinic.id

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr(service.audit_service, "log_event", _boom)

    with pytest.raises(RuntimeError):
        await service.create_movement(
            medicine_id, batch_id,
            MedicineStockMovementCreate(movement_type="Adjustment", quantity_delta=-10, reason="should roll back"),
            clinic_id=clinic_id, actor=owner,
        )
    await db_session.rollback()

    refreshed = await service.get_batch(medicine_id, batch_id, clinic_id=clinic_id)
    assert refreshed.quantity_remaining == 100  # unchanged - the failed call's update never committed

    movements = await service.list_movements(medicine_id, batch_id, clinic_id=clinic_id)
    assert movements == []  # no orphaned movement row either


# --- 16. Concurrent adjustments do not corrupt quantity ---

async def test_concurrent_adjustments_do_not_corrupt_quantity(
    client: AsyncClient, make_clinic_with_owner, engine
) -> None:
    from app.services.medicine_service import MedicineService
    from app.schemas.medicine import MedicineStockMovementCreate

    clinic, owner, _password = await make_clinic_with_owner()
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with session_maker() as setup_session:
        setup_service = MedicineService(setup_session)
        from app.schemas.medicine import MedicineBatchCreate, MedicineCreate

        medicine = await setup_service.create(MedicineCreate(**_medicine_payload()), clinic_id=clinic.id, actor=owner)
        batch = await setup_service.create_batch(
            medicine.id,
            MedicineBatchCreate(**_batch_payload(quantity_received=100, quantity_remaining=100)),
            clinic_id=clinic.id, actor=owner,
        )

    async def _adjust(delta: int, reason: str):
        async with session_maker() as session:
            service = MedicineService(session)
            await service.create_movement(
                medicine.id, batch.id,
                MedicineStockMovementCreate(movement_type="Adjustment", quantity_delta=delta, reason=reason),
                clinic_id=clinic.id, actor=owner,
            )

    # Two concurrent adjustments against the SAME batch - the row lock
    # (`SELECT ... FOR UPDATE`) must serialize them so neither reads a stale
    # quantity_remaining.
    await asyncio.gather(_adjust(-30, "concurrent A"), _adjust(-20, "concurrent B"))

    async with session_maker() as check_session:
        check_service = MedicineService(check_session)
        final_batch = await check_service.get_batch(medicine.id, batch.id, clinic_id=clinic.id)
        assert final_batch.quantity_remaining == 50  # 100 - 30 - 20, never corrupted

        movements = await check_service.list_movements(medicine.id, batch.id, clinic_id=clinic.id)
        assert len(movements) == 2
        assert {m.resulting_quantity for m in movements} == {70, 50}


# --- 17. Movement history ordering ---

async def test_movement_history_ordering_is_reverse_chronological(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers, quantity_received=100, quantity_remaining=100)

    await client.post(_movements_url(medicine_id, batch_id), headers=headers, json={"movement_type": "Adjustment", "quantity_delta": -1, "reason": "first"})
    await client.post(_movements_url(medicine_id, batch_id), headers=headers, json={"movement_type": "Adjustment", "quantity_delta": -1, "reason": "second"})
    await client.post(_movements_url(medicine_id, batch_id), headers=headers, json={"movement_type": "Adjustment", "quantity_delta": -1, "reason": "third"})

    listed = await client.get(_movements_url(medicine_id, batch_id), headers=headers)
    reasons = [m["reason"] for m in listed.json()["items"]]
    assert reasons == ["third", "second", "first"]


# --- 18. Existing Phase 1 batch behavior remains compatible ---

async def test_phase1_batch_edit_still_works_and_ignores_quantity_fields(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_id, batch_id = await _create_medicine_and_batch(client, headers)

    resp = await client.put(
        f"/api/v1/medicines/{medicine_id}/batches/{batch_id}", headers=headers,
        json={"supplier": "Updated Supplier", "quantity_remaining": 999999},  # extra field silently ignored
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["supplier"] == "Updated Supplier"
    assert resp.json()["quantity_remaining"] == 100  # untouched by the ignored field

    listed = await client.get(f"/api/v1/medicines/{medicine_id}/batches", headers=headers)
    assert listed.status_code == 200, listed.text
