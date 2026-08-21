"""Medicine Inventory Phase 3: expiry-tier computation, notification
generation/dedup, the daily background-check guard (restart/concurrency
safety), notification API (visibility/read-state/clinic isolation), and
medicine-level stock/expiry filters and dashboard stats."""

import asyncio
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password
from app.models.role import Role
from app.schemas.medicine import MedicineBatchCreate, MedicineCreate
from app.services.medicine_expiry_service import MedicineExpiryCheckService
from app.services.medicine_service import MedicineService
from app.services.notification_service import NotificationService

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
    payload = {"generic_name": "Amoxicillin", "brand_name": None, "strength": "500mg", "dosage_form": "Capsule", "unit": "capsule", "reorder_level": 50}
    payload.update(overrides)
    return payload


def _batch_payload(**overrides) -> dict:
    payload = {
        "batch_number": "AMX-2407", "quantity_received": 18, "quantity_remaining": 18,
        "expiry_date": (date.today() + timedelta(days=200)).isoformat(),
        "received_date": date.today().isoformat(), "supplier": None, "cost_per_unit": None,
    }
    payload.update(overrides)
    return payload


async def _create_medicine_batch_direct(session: AsyncSession, *, clinic_id, actor, **batch_overrides):
    service = MedicineService(session)
    medicine = await service.create(MedicineCreate(**_medicine_payload()), clinic_id=clinic_id, actor=actor)
    batch = await service.create_batch(medicine.id, MedicineBatchCreate(**_batch_payload(**batch_overrides)), clinic_id=clinic_id, actor=actor)
    return medicine, batch


# --- 1-4: threshold tiers (defaults 90/60/30/7) ---

@pytest.mark.parametrize("days_out,expected_tier", [(89, 1), (59, 2), (29, 3), (6, 4)])
async def test_threshold_tier_generates_correct_warning(
    make_clinic_with_owner, db_session: AsyncSession, days_out, expected_tier
) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    _medicine, batch = await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=days_out)).isoformat()
    )
    batch_id, medicine_id, clinic_id = batch.id, batch.medicine_id, clinic.id

    service = MedicineExpiryCheckService(db_session)
    ran = await service.run_for_clinic(clinic_id, today=date.today())
    assert ran is True

    refreshed = await MedicineService(db_session).get_batch(medicine_id, batch_id, clinic_id=clinic_id)
    assert refreshed.last_alerted_expiry_tier == expected_tier

    notifications, total = await NotificationService(db_session).repo.list_visible(
        clinic_id, role_name="Receptionist", user_id=owner.id, is_privileged=False
    )
    assert total == 1
    assert "Expiring Soon" in notifications[0].title
    assert batch.batch_number in notifications[0].body
    assert "18 units remaining" in notifications[0].body


# --- 5: expired batch generates expired alert ---

async def test_expired_batch_generates_expired_alert(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    _medicine, batch = await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() - timedelta(days=1)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())

    refreshed = await MedicineService(db_session).get_batch(batch.medicine_id, batch.id, clinic_id=clinic.id)
    assert refreshed.last_alerted_expiry_tier == 5

    notifications, total = await NotificationService(db_session).repo.list_visible(
        clinic.id, role_name="Doctor", user_id=owner.id, is_privileged=False
    )
    assert total == 1
    assert notifications[0].title == "Medicine Expired"
    assert "expired on" in notifications[0].body


# --- 6: depleted batch generates no alert ---

async def test_depleted_batch_generates_no_alert(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    _medicine, batch = await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner,
        quantity_received=10, quantity_remaining=0, expiry_date=(date.today() + timedelta(days=3)).isoformat(),
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())

    refreshed = await MedicineService(db_session).get_batch(batch.medicine_id, batch.id, clinic_id=clinic.id)
    assert refreshed.last_alerted_expiry_tier == 0

    _notifications, total = await NotificationService(db_session).repo.list_visible(
        clinic.id, role_name="Receptionist", user_id=owner.id, is_privileged=False
    )
    assert total == 0


# --- 7: recalled batch is not silently overwritten ---

async def test_recalled_batch_not_overwritten(make_clinic_with_owner, db_session: AsyncSession) -> None:
    from app.models.medicine import MedicineBatchStatus
    from app.schemas.medicine import MedicineBatchUpdate

    clinic, owner, _password = await make_clinic_with_owner()
    medicine, batch = await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=3)).isoformat()
    )
    medicine_service = MedicineService(db_session)
    recalled = await medicine_service.update_batch(
        medicine.id, batch.id, MedicineBatchUpdate(status=MedicineBatchStatus.RECALLED), clinic_id=clinic.id, actor=owner
    )
    assert recalled.status == MedicineBatchStatus.RECALLED

    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())

    refreshed = await medicine_service.get_batch(medicine.id, batch.id, clinic_id=clinic.id)
    assert refreshed.status == MedicineBatchStatus.RECALLED  # never overwritten
    assert refreshed.last_alerted_expiry_tier == 0  # and no alert was generated for it

    _n, total = await NotificationService(db_session).repo.list_visible(
        clinic.id, role_name="Receptionist", user_id=owner.id, is_privileged=False
    )
    assert total == 0


# --- 8: same tier does not generate duplicate alert ---

async def test_same_tier_does_not_duplicate(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    _medicine, batch = await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=85)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())
    # A later "day" where the batch is still comfortably within tier 1 -
    # must not regenerate the tier-1 alert.
    await service.run_for_clinic(clinic.id, today=date.today() + timedelta(days=1))

    _n, total = await NotificationService(db_session).repo.list_visible(
        clinic.id, role_name="Receptionist", user_id=owner.id, is_privileged=False
    )
    assert total == 1


# --- 9: crossing into a new tier generates one new alert ---

async def test_crossing_tier_generates_one_new_alert(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    _medicine, batch = await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=89)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())  # tier 1

    refreshed = await MedicineService(db_session).get_batch(_medicine.id, batch.id, clinic_id=clinic.id)
    assert refreshed.last_alerted_expiry_tier == 1

    # Jump forward to a "day" where the same batch is now within tier 2.
    await service.run_for_clinic(clinic.id, today=date.today() + timedelta(days=31))

    refreshed = await MedicineService(db_session).get_batch(_medicine.id, batch.id, clinic_id=clinic.id)
    assert refreshed.last_alerted_expiry_tier == 2

    _n, total = await NotificationService(db_session).repo.list_visible(
        clinic.id, role_name="Receptionist", user_id=owner.id, is_privileged=False
    )
    assert total == 2  # one for tier 1, one new one for tier 2 - no backfill of intermediate tiers


# --- 10: expired alert generated only once ---

async def test_expired_alert_generated_only_once(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    _medicine, batch = await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() - timedelta(days=1)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())
    await service.run_for_clinic(clinic.id, today=date.today() + timedelta(days=1))

    _n, total = await NotificationService(db_session).repo.list_visible(
        clinic.id, role_name="Doctor", user_id=owner.id, is_privileged=False
    )
    assert total == 1


# --- 11: multiple batches for the same medicine handled independently ---

async def test_multiple_batches_handled_independently(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _password = await make_clinic_with_owner()
    medicine_service = MedicineService(db_session)
    medicine = await medicine_service.create(MedicineCreate(**_medicine_payload()), clinic_id=clinic.id, actor=owner)
    fine_batch = await medicine_service.create_batch(
        medicine.id, MedicineBatchCreate(**_batch_payload(batch_number="FINE-1", expiry_date=(date.today() + timedelta(days=200)).isoformat())),
        clinic_id=clinic.id, actor=owner,
    )
    near_batch = await medicine_service.create_batch(
        medicine.id, MedicineBatchCreate(**_batch_payload(batch_number="NEAR-1", expiry_date=(date.today() + timedelta(days=5)).isoformat())),
        clinic_id=clinic.id, actor=owner,
    )

    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())

    fine_refreshed = await medicine_service.get_batch(medicine.id, fine_batch.id, clinic_id=clinic.id)
    near_refreshed = await medicine_service.get_batch(medicine.id, near_batch.id, clinic_id=clinic.id)
    assert fine_refreshed.last_alerted_expiry_tier == 0
    assert near_refreshed.last_alerted_expiry_tier == 4


# --- 12: medicine with one valid + one expired batch reports correctly ---

async def test_medicine_with_valid_and_expired_batch_reports_correctly(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    await client.post(f"/api/v1/medicines/{medicine['id']}/batches", headers=headers, json=_batch_payload(batch_number="VALID-1"))
    await client.post(
        f"/api/v1/medicines/{medicine['id']}/batches", headers=headers,
        json=_batch_payload(batch_number="EXPIRED-1", expiry_date=(date.today() - timedelta(days=5)).isoformat()),
    )

    all_resp = await client.get("/api/v1/medicines", headers=headers)
    row = next(m for m in all_resp.json()["items"] if m["id"] == medicine["id"])
    assert row["stock_status"] == "expired"  # most-urgent-first summary, not naively "Active"

    in_stock = await client.get("/api/v1/medicines?stock_status=in_stock", headers=headers)
    assert any(m["id"] == medicine["id"] for m in in_stock.json()["items"])  # still available via the valid batch

    expired = await client.get("/api/v1/medicines?stock_status=expired", headers=headers)
    assert any(m["id"] == medicine["id"] for m in expired.json()["items"])


# --- 13: clinic isolation ---

async def test_clinic_isolation_for_expiry_alerts(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic_a, owner_a, _pw = await make_clinic_with_owner()
    clinic_b, owner_b, _pw2 = await make_clinic_with_owner()
    await _create_medicine_batch_direct(
        db_session, clinic_id=clinic_a.id, actor=owner_a, expiry_date=(date.today() + timedelta(days=5)).isoformat()
    )

    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic_a.id, today=date.today())
    await service.run_for_clinic(clinic_b.id, today=date.today())

    b_notifications, b_total = await NotificationService(db_session).repo.list_visible(
        clinic_b.id, role_name="Receptionist", user_id=owner_b.id, is_privileged=False
    )
    assert b_total == 0
    assert b_notifications == []


async def test_clinic_isolation_via_api(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic_a, owner_a, headers_a = await _owner_headers(client, make_clinic_with_owner)
    _clinic_b, _owner_b, headers_b = await _owner_headers(client, make_clinic_with_owner)
    await _create_medicine_batch_direct(
        db_session, clinic_id=clinic_a.id, actor=owner_a, expiry_date=(date.today() + timedelta(days=5)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic_a.id, today=date.today())

    resp_b = await client.get("/api/v1/notifications", headers=headers_b)
    assert resp_b.status_code == 200, resp_b.text
    assert resp_b.json()["items"] == []

    stats_b = await client.get("/api/v1/medicines/stats", headers=headers_b)
    assert stats_b.json() == {"expiring_soon": 0, "expired": 0, "low_stock": 0, "out_of_stock": 0}


# --- 14: role visibility ---

async def test_role_visibility_for_notifications(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=5)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())

    doc_email, _doc = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Doctor", password="DocPass123!")
    doc_headers = {"Authorization": f"Bearer {await _login(client, doc_email, 'DocPass123!')}"}
    doc_resp = await client.get("/api/v1/notifications", headers=doc_headers)
    assert doc_resp.status_code == 200
    assert len(doc_resp.json()["items"]) == 1

    cashier_email, _cashier = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Cashier", password="CashPass123!")
    cashier_headers = {"Authorization": f"Bearer {await _login(client, cashier_email, 'CashPass123!')}"}
    cashier_resp = await client.get("/api/v1/notifications", headers=cashier_headers)
    assert cashier_resp.status_code == 403

    # Owner sees every notification regardless of target_role (privileged superset).
    owner_resp = await client.get("/api/v1/notifications", headers=owner_headers)
    assert len(owner_resp.json()["items"]) == 2  # one Receptionist-targeted + one Doctor-targeted


# --- 15/16: per-user read state + mark one read ---

async def test_per_user_read_state_and_mark_one_read(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _owner_headers_ = await _owner_headers(client, make_clinic_with_owner)
    await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=5)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    await service.run_for_clinic(clinic.id, today=date.today())

    rec_a_email, _a = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist", password="RecA12345!")
    rec_a_headers = {"Authorization": f"Bearer {await _login(client, rec_a_email, 'RecA12345!')}"}
    rec_b_email, _b = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist", password="RecB12345!")
    rec_b_headers = {"Authorization": f"Bearer {await _login(client, rec_b_email, 'RecB12345!')}"}

    listed = (await client.get("/api/v1/notifications", headers=rec_a_headers)).json()["items"]
    assert len(listed) == 1 and listed[0]["is_read"] is False
    notification_id = listed[0]["id"]

    mark_resp = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=rec_a_headers)
    assert mark_resp.status_code == 204, mark_resp.text

    a_after = (await client.get("/api/v1/notifications", headers=rec_a_headers)).json()["items"]
    assert a_after[0]["is_read"] is True

    b_after = (await client.get("/api/v1/notifications", headers=rec_b_headers)).json()["items"]
    assert b_after[0]["is_read"] is False  # Receptionist B still sees it as unread


# --- 17: mark all read ---

async def test_mark_all_read(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine_service = MedicineService(db_session)
    medicine = await medicine_service.create(MedicineCreate(**_medicine_payload()), clinic_id=clinic.id, actor=owner)
    await medicine_service.create_batch(
        medicine.id, MedicineBatchCreate(**_batch_payload(batch_number="A", expiry_date=(date.today() + timedelta(days=5)).isoformat())),
        clinic_id=clinic.id, actor=owner,
    )
    await medicine_service.create_batch(
        medicine.id, MedicineBatchCreate(**_batch_payload(batch_number="B", expiry_date=(date.today() - timedelta(days=1)).isoformat())),
        clinic_id=clinic.id, actor=owner,
    )
    await MedicineExpiryCheckService(db_session).run_for_clinic(clinic.id, today=date.today())

    unread_before = await client.get("/api/v1/notifications/unread-count", headers=headers)
    # Owner is privileged (sees both the Receptionist- and Doctor-targeted
    # alert for each batch) - 2 batches x 2 target roles = 4.
    assert unread_before.json()["unread_count"] == 4

    mark_all = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert mark_all.status_code == 200, mark_all.text
    assert mark_all.json()["marked_count"] == 4

    unread_after = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert unread_after.json()["unread_count"] == 0


# --- 18: notification unread count ---

async def test_unread_count_endpoint(client: AsyncClient, make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, headers = await _owner_headers(client, make_clinic_with_owner)
    zero = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert zero.json()["unread_count"] == 0

    await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=5)).isoformat()
    )
    await MedicineExpiryCheckService(db_session).run_for_clinic(clinic.id, today=date.today())

    one = await client.get("/api/v1/notifications/unread-count", headers=headers)
    assert one.json()["unread_count"] == 2  # Owner sees both the Receptionist- and Doctor-targeted alerts


# --- 19: dashboard expiry counts ---

async def test_dashboard_expiry_counts(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    medicine = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload())).json()
    await client.post(
        f"/api/v1/medicines/{medicine['id']}/batches", headers=headers,
        json=_batch_payload(batch_number="NEAR", expiry_date=(date.today() + timedelta(days=5)).isoformat()),
    )
    medicine2 = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload(generic_name="Paracetamol"))).json()
    await client.post(
        f"/api/v1/medicines/{medicine2['id']}/batches", headers=headers,
        json=_batch_payload(batch_number="EXP", expiry_date=(date.today() - timedelta(days=1)).isoformat()),
    )

    stats = (await client.get("/api/v1/medicines/stats", headers=headers)).json()
    assert stats["expiring_soon"] == 1
    assert stats["expired"] == 1


# --- 20/21: low-stock / out-of-stock counts ---

async def test_low_stock_and_out_of_stock_counts(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)

    low = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload(generic_name="LowStockMed", reorder_level=50))).json()
    await client.post(f"/api/v1/medicines/{low['id']}/batches", headers=headers, json=_batch_payload(batch_number="L1", quantity_received=10, quantity_remaining=10))

    out = (await client.post("/api/v1/medicines", headers=headers, json=_medicine_payload(generic_name="OutOfStockMed", reorder_level=50))).json()
    await client.post(f"/api/v1/medicines/{out['id']}/batches", headers=headers, json=_batch_payload(batch_number="O1", quantity_received=10, quantity_remaining=0))

    stats = (await client.get("/api/v1/medicines/stats", headers=headers)).json()
    assert stats["low_stock"] == 1
    assert stats["out_of_stock"] == 1

    low_resp = await client.get("/api/v1/medicines?stock_status=low_stock", headers=headers)
    assert {m["id"] for m in low_resp.json()["items"]} == {low["id"]}

    out_resp = await client.get("/api/v1/medicines?stock_status=out_of_stock", headers=headers)
    assert {m["id"] for m in out_resp.json()["items"]} == {out["id"]}


# --- 22: threshold validation ---

async def test_threshold_validation(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)

    non_descending = await client.put(
        "/api/v1/clinic-settings", headers=headers,
        json={
            "medicine_expiry_warning_days_tier1": 30, "medicine_expiry_warning_days_tier2": 60,
            "medicine_expiry_warning_days_tier3": 20, "medicine_expiry_warning_days_tier4": 5,
        },
    )
    assert non_descending.status_code == 422, non_descending.text

    negative = await client.put("/api/v1/clinic-settings", headers=headers, json={"medicine_expiry_warning_days_tier4": -1})
    assert negative.status_code == 422, negative.text

    zero = await client.put("/api/v1/clinic-settings", headers=headers, json={"medicine_expiry_warning_days_tier4": 0})
    assert zero.status_code == 422, zero.text

    valid = await client.put(
        "/api/v1/clinic-settings", headers=headers,
        json={
            "medicine_expiry_warning_days_tier1": 120, "medicine_expiry_warning_days_tier2": 60,
            "medicine_expiry_warning_days_tier3": 30, "medicine_expiry_warning_days_tier4": 10,
        },
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["medicine_expiry_warning_days_tier1"] == 120

    # Partial update validated against the MERGED (existing + new) values.
    partial_conflict = await client.put("/api/v1/clinic-settings", headers=headers, json={"medicine_expiry_warning_days_tier1": 5})
    assert partial_conflict.status_code == 422, partial_conflict.text


# --- 23: restart/day guard does not duplicate ---

async def test_daily_guard_prevents_duplicate_runs_same_day(make_clinic_with_owner, db_session: AsyncSession) -> None:
    clinic, owner, _pw = await make_clinic_with_owner()
    await _create_medicine_batch_direct(
        db_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=5)).isoformat()
    )
    service = MedicineExpiryCheckService(db_session)
    today = date.today()

    first_ran = await service.run_for_clinic(clinic.id, today=today)
    # Simulates a restart: same service, same date, called again.
    second_ran = await service.run_for_clinic(clinic.id, today=today)
    assert first_ran is True
    assert second_ran is False

    _n, total = await NotificationService(db_session).repo.list_visible(
        clinic.id, role_name="Receptionist", user_id=owner.id, is_privileged=False
    )
    assert total == 1  # not 2


# --- 24: concurrent daily checks do not create duplicates ---

async def test_concurrent_daily_checks_do_not_duplicate(make_clinic_with_owner, engine) -> None:
    session_maker = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    clinic, owner, _pw = await make_clinic_with_owner()

    async with session_maker() as setup_session:
        await _create_medicine_batch_direct(
            setup_session, clinic_id=clinic.id, actor=owner, expiry_date=(date.today() + timedelta(days=5)).isoformat()
        )

    today = date.today()

    async def _run():
        async with session_maker() as session:
            await MedicineExpiryCheckService(session).run_for_clinic(clinic.id, today=today)

    # Two "workers" racing to run the same clinic's check on the same day -
    # the SELECT ... FOR UPDATE guard must serialize them so only one
    # actually processes.
    await asyncio.gather(_run(), _run())

    async with session_maker() as check_session:
        _n, total = await NotificationService(check_session).repo.list_visible(
            clinic.id, role_name="Receptionist", user_id=owner.id, is_privileged=False
        )
        assert total == 1  # not 2 - no duplicate from the race
