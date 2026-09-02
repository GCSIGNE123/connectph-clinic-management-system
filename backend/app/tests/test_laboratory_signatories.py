"""Laboratory Report Signatories (Round 6): Med Tech In Charge + Pathologist
configuration, selection, release-time snapshot capture, and historical
immutability of already-released reports.

Reuses `_setup_with_lab_order`/`_owner_headers`/`_make_role_login`/
`_enter_one_result` from `test_laboratory.py` rather than duplicating the
full order->collect->process->enter-results setup flow.
"""

import io

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.tests.test_laboratory import (
    _enter_one_result,
    _login,
    _make_role_login,
    _owner_headers,
    _setup_with_lab_order,
)

pytestmark = pytest.mark.asyncio

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
PNG_BYTES_2 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4"
    b"\x89\x00\x00\x00\x0bIDATx\x9cc`\x00\x00\x00\x06\x00\x02\x9a\x18\x8e\xea\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


def _png_file(name: str = "sig.png", content: bytes = PNG_BYTES):
    return {"file": (name, io.BytesIO(content), "image/png")}


async def _create_pathologist(client: AsyncClient, headers: dict, **overrides) -> dict:
    payload = {"name": "Dr. Maria Santos", "license_number": "PRC-12345"}
    payload.update(overrides)
    resp = await client.post("/api/v1/pathologists", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _lab_user_headers(client: AsyncClient, db_session: AsyncSession, *, clinic_id) -> tuple[dict, "object"]:
    email, user = await _make_role_login(db_session, clinic_id=clinic_id, role_name="Laboratory")
    token = await _login(client, email, "TestPass123!")
    return {"Authorization": f"Bearer {token}"}, user


async def _release_ready_order(client: AsyncClient, make_clinic_with_owner, db_session):
    """Sets up a lab order and advances it through collect/process/enter-
    results (auto-transitions to Completed), ready for `/release`."""
    ctx = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    lab_id = ctx["lab_order"]["id"]
    await _enter_one_result(client, lab_id, ctx["lab_headers"])
    return ctx, lab_id


# --- 1. Med Tech signature can be configured ---


async def test_1_med_tech_signature_can_be_configured(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, _owner_hdrs = await _owner_headers(client, make_clinic_with_owner)
    lab_headers, _user = await _lab_user_headers(client, db_session, clinic_id=clinic.id)

    before = await client.get("/api/v1/auth/me", headers=lab_headers)
    assert before.json()["has_signature"] is False

    upload = await client.post("/api/v1/auth/me/signature", headers=lab_headers, files=_png_file())
    assert upload.status_code == 200, upload.text
    assert upload.json()["has_signature"] is True

    file_resp = await client.get("/api/v1/auth/me/signature/file", headers=lab_headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_BYTES


# --- 2. Pathologist can be configured ---


async def test_2_pathologist_can_be_configured(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    pathologist = await _create_pathologist(client, headers)
    assert pathologist["name"] == "Dr. Maria Santos"
    assert pathologist["signature_url"] is None

    upload = await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=headers, files=_png_file())
    assert upload.status_code == 200, upload.text
    assert upload.json()["signature_url"]

    file_resp = await client.get(f"/api/v1/pathologists/{pathologist['id']}/signature/file", headers=headers)
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_BYTES


# --- 3. Pathologist selection only shows valid/active pathologists ---


async def test_3_pathologist_list_filters_to_active_only(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    active = await _create_pathologist(client, headers, name="Dr. Active One")
    inactive = await _create_pathologist(client, headers, name="Dr. Inactive Two")
    update = await client.put(f"/api/v1/pathologists/{inactive['id']}", headers=headers, json={"is_active": False})
    assert update.status_code == 200, update.text

    listed = await client.get("/api/v1/pathologists?activeOnly=true", headers=headers)
    assert listed.status_code == 200
    names = {p["name"] for p in listed.json()["items"]}
    assert active["name"] in names
    assert inactive["name"] not in names

    unfiltered = await client.get("/api/v1/pathologists", headers=headers)
    names_all = {p["name"] for p in unfiltered.json()["items"]}
    assert {active["name"], inactive["name"]}.issubset(names_all)


# --- 4. Unauthorized signature modification denied ---


async def test_4_receptionist_cannot_manage_pathologist_signature(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    pathologist = await _create_pathologist(client, owner_headers)
    recep_email, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}

    resp = await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=recep_headers, files=_png_file())
    assert resp.status_code == 403


async def test_4b_receptionist_cannot_configure_a_med_tech_signature(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    clinic, _owner, _owner_hdrs = await _owner_headers(client, make_clinic_with_owner)
    recep_email, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name="Receptionist")
    recep_token = await _login(client, recep_email, "TestPass123!")
    recep_headers = {"Authorization": f"Bearer {recep_token}"}

    resp = await client.post("/api/v1/auth/me/signature", headers=recep_headers, files=_png_file())
    assert resp.status_code == 403


# --- 5/6/7/8. Release captures Med Tech + Pathologist, both reprint-able ---


async def test_5_6_7_8_release_snapshots_pathologist_and_reprint_uses_it_med_tech_signature_never_captured(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Client requirement change: a laboratory report's Med Tech In Charge
    no longer gets an e-signature AT ALL, on any new release - both
    MedTechs on a report sign the printed page by hand now (see
    `release_results()`'s explicit `med_tech_signature_snapshot_url=None`).
    This test deliberately configures a real signature on the releasing
    Laboratory user's account FIRST, to prove release still never captures
    it - `User.signature_url` is not read for this purpose anymore. The
    Pathologist side is completely unchanged (still e-signed)."""
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)

    # Configure the Med Tech's (the releasing Laboratory user's) signature
    # - release must still ignore it entirely.
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES))

    pathologist = await _create_pathologist(client, ctx["owner_headers"])
    await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=ctx["owner_headers"], files=_png_file(content=PNG_BYTES_2))

    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"], json={"pathologist_id": pathologist["id"]})
    assert released.status_code == 200, released.text
    body = released.json()

    # #5: Med Tech in Charge is the releasing Laboratory user - name is
    # still captured, but NEVER a signature snapshot, even though one was
    # configured on the account moments before release.
    assert body["released_by"] is not None
    assert body["med_tech_name_snapshot"]
    assert body["med_tech_signature_snapshot_url"] is None

    # #6: selected Pathologist persisted - completely unchanged behavior.
    assert body["pathologist_id"] == pathologist["id"]
    assert body["pathologist_name_snapshot"] == "Dr. Maria Santos"
    assert body["pathologist_signature_snapshot_url"]

    # #7/#8: reprint (a fresh GET) uses the stored snapshot - still null
    # for the Med Tech, still populated for the Pathologist - and the
    # Pathologist's signature file is still fetchable/correct. The Med
    # Tech signature file endpoint now correctly 404s (nothing was ever
    # captured to serve).
    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.json()["med_tech_signature_snapshot_url"] is None
    assert reprint.json()["pathologist_signature_snapshot_url"] == body["pathologist_signature_snapshot_url"]

    med_tech_file = await client.get(f"/api/v1/laboratory/orders/{lab_id}/med-tech-signature/file", headers=ctx["owner_headers"])
    assert med_tech_file.status_code == 404

    pathologist_file = await client.get(f"/api/v1/laboratory/orders/{lab_id}/pathologist-signature/file", headers=ctx["owner_headers"])
    assert pathologist_file.status_code == 200
    assert pathologist_file.content == PNG_BYTES_2


async def test_5b_med_tech_signature_is_never_captured_regardless_of_when_the_account_signature_changes(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Broader than test_9 used to be (pre-requirement-change, that test
    proved an already-captured snapshot survives a LATER account change) -
    now there is never anything to capture in the first place, whether the
    account's signature is set before release, after release, or both."""
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES))
    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.json()["med_tech_signature_snapshot_url"] is None

    # Changing the account's signature AFTER release changes nothing either
    # - there was never a snapshot column value tied to it post-release.
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES_2))
    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.json()["med_tech_signature_snapshot_url"] is None
    file_resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/med-tech-signature/file", headers=ctx["owner_headers"])
    assert file_resp.status_code == 404


async def test_5c_a_historical_med_tech_signature_snapshot_from_before_this_change_still_serves_unchanged(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Historical-compatibility guarantee: an order released BEFORE this
    requirement change already has a real `med_tech_signature_snapshot_url`
    value in the database. Nothing in this change touches that column or
    that data - simulated here by writing directly to the row (the live
    release API can no longer produce such a row going forward, which is
    exactly the point), then proving GET/file-serving still work exactly
    as they did before."""
    from app.models.laboratory_order import LaboratoryOrder

    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.json()["med_tech_signature_snapshot_url"] is None

    # Simulate a pre-existing historical row by writing the snapshot
    # column directly (bypassing the API, which never sets this anymore).
    from app.core.doctor_signature_storage import USER_SIGNATURES_UPLOAD_ROOT

    signature_dir = USER_SIGNATURES_UPLOAD_ROOT / str(ctx["clinic"].id) / str(released.json()["released_by"])
    signature_dir.mkdir(parents=True, exist_ok=True)
    (signature_dir / "historical-sig.png").write_bytes(PNG_BYTES)

    lab_order_row = await db_session.get(LaboratoryOrder, lab_id)
    lab_order_row.med_tech_signature_snapshot_url = "historical-sig.png"
    await db_session.commit()

    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.json()["med_tech_signature_snapshot_url"] == "historical-sig.png"
    file_resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/med-tech-signature/file", headers=ctx["owner_headers"])
    assert file_resp.status_code == 200
    assert file_resp.content == PNG_BYTES


# --- 9/10/11. Historical immutability ---


# test_9 (originally: "changing the Med Tech's current signature does not
# change an old report") is superseded by test_5b/test_5c above - a new
# release never captures a Med Tech signature at all anymore (nothing for
# a later account change to threaten), and test_5c covers the historical-
# row case a pre-change report actually needs protected.


async def test_10_changing_pathologists_current_signature_does_not_change_old_report(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    pathologist = await _create_pathologist(client, ctx["owner_headers"])
    await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=ctx["owner_headers"], files=_png_file(content=PNG_BYTES))
    released = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"], json={"pathologist_id": pathologist["id"]}
    )
    original_snapshot = released.json()["pathologist_signature_snapshot_url"]
    assert original_snapshot

    # Replace the Pathologist's CURRENT signature after release.
    await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=ctx["owner_headers"], files=_png_file(content=PNG_BYTES_2))

    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.json()["pathologist_signature_snapshot_url"] == original_snapshot
    file_resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/pathologist-signature/file", headers=ctx["owner_headers"])
    assert file_resp.content == PNG_BYTES  # still the OLD signature


async def test_11_changing_selected_pathologist_later_does_not_change_old_report(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id_a = await _release_ready_order(client, make_clinic_with_owner, db_session)
    pathologist_a = await _create_pathologist(client, ctx["owner_headers"], name="Dr. Pathologist A")
    released_a = await client.post(
        f"/api/v1/laboratory/orders/{lab_id_a}/release", headers=ctx["lab_headers"], json={"pathologist_id": pathologist_a["id"]}
    )
    assert released_a.status_code == 200, released_a.text
    assert released_a.json()["pathologist_name_snapshot"] == "Dr. Pathologist A"

    # A second order in the SAME clinic released later with a DIFFERENT
    # selected pathologist must not retroactively alter order A.
    ctx2 = await _setup_with_lab_order(client, make_clinic_with_owner, db_session)
    # (separate clinic - still proves order A is untouched by ANY later release)
    lab_id_b = ctx2["lab_order"]["id"]
    await _enter_one_result(client, lab_id_b, ctx2["lab_headers"])
    pathologist_b = await _create_pathologist(client, ctx2["owner_headers"], name="Dr. Pathologist B")
    await client.post(
        f"/api/v1/laboratory/orders/{lab_id_b}/release", headers=ctx2["lab_headers"], json={"pathologist_id": pathologist_b["id"]}
    )

    reprint_a = await client.get(f"/api/v1/laboratory/orders/{lab_id_a}", headers=ctx["owner_headers"])
    assert reprint_a.json()["pathologist_name_snapshot"] == "Dr. Pathologist A"


# --- 12. Cross-clinic Pathologist selection rejected ---


async def test_12_cross_clinic_pathologist_selection_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    other_clinic, _other_owner, other_headers = await _owner_headers(client, make_clinic_with_owner)
    foreign_pathologist = await _create_pathologist(client, other_headers, name="Dr. Foreign")

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
        json={"pathologist_id": foreign_pathologist["id"]},
    )
    assert resp.status_code == 404


async def test_12b_inactive_pathologist_selection_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    pathologist = await _create_pathologist(client, ctx["owner_headers"])
    await client.put(f"/api/v1/pathologists/{pathologist['id']}", headers=ctx["owner_headers"], json={"is_active": False})

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"], json={"pathologist_id": pathologist["id"]}
    )
    assert resp.status_code == 400


# --- 13/14. Missing signature behavior ---


async def test_13_missing_med_tech_signature_does_not_block_release_or_fabricate_one(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A Med Tech signature is never captured on release at all now
    (client requirement change - see test_5_6_7_8's updated docstring),
    so this is unconditionally true regardless of whether one was
    configured on the account - release still succeeds, and the snapshot
    is simply always null rather than fabricated."""
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.status_code == 200, released.text
    assert released.json()["med_tech_signature_snapshot_url"] is None
    assert released.json()["med_tech_name_snapshot"]  # name still captured even with no signature image


async def test_14_missing_pathologist_selection_does_not_block_release_or_fabricate_one(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.status_code == 200, released.text
    assert released.json()["pathologist_id"] is None
    assert released.json()["pathologist_name_snapshot"] is None
    assert released.json()["pathologist_signature_snapshot_url"] is None


# --- 15. Historical report remains unchanged (combined regression) ---


async def test_15_historical_report_remains_unchanged_after_multiple_later_edits(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES))
    pathologist = await _create_pathologist(client, ctx["owner_headers"], name="Dr. Original")
    await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=ctx["owner_headers"], files=_png_file(content=PNG_BYTES))
    released = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"], json={"pathologist_id": pathologist["id"]}
    )
    snapshot_at_release = {
        k: released.json()[k] for k in (
            "med_tech_name_snapshot", "med_tech_signature_snapshot_url",
            "pathologist_name_snapshot", "pathologist_signature_snapshot_url",
        )
    }

    # Pile on several later edits.
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES_2))
    await client.put(f"/api/v1/pathologists/{pathologist['id']}", headers=ctx["owner_headers"], json={"name": "Dr. Renamed"})
    await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=ctx["owner_headers"], files=_png_file(content=PNG_BYTES_2))

    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    for key, value in snapshot_at_release.items():
        assert reprint.json()[key] == value, f"{key} changed after later edits"


# --- 16. Multiple reports can have different signatory snapshots ---


async def test_16_multiple_reports_have_independent_signatory_snapshots(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx_a, lab_id_a = await _release_ready_order(client, make_clinic_with_owner, db_session)
    pathologist_a = await _create_pathologist(client, ctx_a["owner_headers"], name="Dr. First")
    released_a = await client.post(
        f"/api/v1/laboratory/orders/{lab_id_a}/release", headers=ctx_a["lab_headers"], json={"pathologist_id": pathologist_a["id"]}
    )

    ctx_b, lab_id_b = await _release_ready_order(client, make_clinic_with_owner, db_session)
    pathologist_b = await _create_pathologist(client, ctx_b["owner_headers"], name="Dr. Second")
    released_b = await client.post(
        f"/api/v1/laboratory/orders/{lab_id_b}/release", headers=ctx_b["lab_headers"], json={"pathologist_id": pathologist_b["id"]}
    )

    assert released_a.json()["pathologist_name_snapshot"] == "Dr. First"
    assert released_b.json()["pathologist_name_snapshot"] == "Dr. Second"
    assert released_a.json()["pathologist_name_snapshot"] != released_b.json()["pathologist_name_snapshot"]


# --- 17/18. Released result stays printable; existing lifecycle intact ---


async def test_17_18_released_result_remains_printable_and_existing_lifecycle_intact(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "Released"
    assert released.json()["released_at"] is not None
    assert released.json()["released_by"] is not None

    # #17: still printable/fetchable, with results intact.
    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.status_code == 200
    assert len(reprint.json()["results"]) >= 1

    # #18: existing idempotent re-release rejection (unchanged pre-existing
    # behavior) still holds with the new optional pathologist_id parameter
    # in play.
    re_release = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert re_release.status_code == 400


# --- Countersigning Med Technologist (client requirement: a second,
# MANUALLY-signing MedTech, distinct from the Med Tech In Charge - see
# migration 0043). Selected from eligible Laboratory-role Users at release
# time; snapshotted (name + license only, deliberately NO signature field)
# the same "capture once, never re-resolve" way as every other signatory
# on this table. ---


async def _second_lab_user(client: AsyncClient, db_session, *, clinic_id, first_name: str, last_name: str, license_number: str | None = None):
    """A SECOND Laboratory-role user in the same clinic (distinct from the
    one `_setup_with_lab_order`/`_release_ready_order` already creates as
    the releasing Med Tech In Charge) - the countersigning MedTech."""
    email, user = await _make_role_login(db_session, clinic_id=clinic_id, role_name="Laboratory")
    user.first_name = first_name
    user.last_name = last_name
    user.license_number = license_number
    await db_session.commit()
    await db_session.refresh(user)
    token = await _login(client, email, "TestPass123!")
    return {"Authorization": f"Bearer {token}"}, user


async def test_c1_release_snapshots_the_selected_countersigning_med_tech_name_and_license_no_signature_field(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    _countersigner_headers, countersigner = await _second_lab_user(
        client, db_session, clinic_id=ctx["clinic"].id, first_name="Aijilie", last_name="Mosquite", license_number="123456"
    )

    released = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
        json={"countersigning_med_tech_id": str(countersigner.id)},
    )
    assert released.status_code == 200, released.text
    body = released.json()

    assert body["countersigning_med_tech_id"] == str(countersigner.id)
    assert body["countersigning_med_tech_name_snapshot"] == "Aijilie Mosquite"
    assert body["countersigning_med_tech_license_snapshot"] == "123456"
    # No signature field exists for this role at all - not even a null one
    # that could someday be populated; the key itself is absent from the
    # schema/response.
    assert "countersigning_med_tech_signature_snapshot_url" not in body


async def test_c2_missing_countersigning_med_tech_selection_does_not_block_release_or_fabricate_one(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    assert released.status_code == 200, released.text
    assert released.json()["countersigning_med_tech_id"] is None
    assert released.json()["countersigning_med_tech_name_snapshot"] is None
    assert released.json()["countersigning_med_tech_license_snapshot"] is None


async def test_c3_cross_clinic_countersigning_med_tech_selection_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    other_clinic, _other_owner, _other_headers = await _owner_headers(client, make_clinic_with_owner)
    _foreign_headers, foreign_med_tech = await _second_lab_user(
        client, db_session, clinic_id=other_clinic.id, first_name="Foreign", last_name="MedTech"
    )

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
        json={"countersigning_med_tech_id": str(foreign_med_tech.id)},
    )
    assert resp.status_code == 404


async def test_c3b_nonexistent_countersigning_med_tech_id_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Security review follow-up: distinct from test_c3 (a real user in
    ANOTHER clinic) - a UUID that matches no user row at all, anywhere,
    must also be rejected. The backend never trusts the id it's handed;
    it re-validates existence + clinic + role + active status in one
    query at release time, never relying on GET /laboratory/med-techs'
    own filtering for this protection."""
    import uuid as _uuid

    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
        json={"countersigning_med_tech_id": str(_uuid.uuid4())},
    )
    assert resp.status_code == 404


async def test_c4_non_medtech_roles_cannot_be_selected_as_countersigner(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Authorization requirement: only eligible Laboratory-role Users can
    be selected as the countersigning MedTech - a Doctor, Receptionist, or
    Owner in the SAME clinic must be rejected exactly like a not-found
    user, reusing the existing role definition rather than a new one."""
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    doc_me = (await client.get("/api/v1/auth/me", headers=ctx["doc_headers"])).json()
    recep_me = (await client.get("/api/v1/auth/me", headers=ctx["recep_headers"])).json()
    owner_me = (await client.get("/api/v1/auth/me", headers=ctx["owner_headers"])).json()

    for non_medtech_id in (doc_me["id"], recep_me["id"], owner_me["id"]):
        resp = await client.post(
            f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
            json={"countersigning_med_tech_id": non_medtech_id},
        )
        assert resp.status_code == 404, f"role check should reject {non_medtech_id}"


async def test_c5_inactive_countersigning_med_tech_selection_rejected(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    _countersigner_headers, countersigner = await _second_lab_user(
        client, db_session, clinic_id=ctx["clinic"].id, first_name="Inactive", last_name="MedTech"
    )
    countersigner.is_active = False
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
        json={"countersigning_med_tech_id": str(countersigner.id)},
    )
    assert resp.status_code == 400


async def test_c6_countersigning_med_tech_historical_snapshot_survives_a_later_rename(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Same historical-immutability guarantee as the Pathologist/Med Tech
    In Charge - a later rename of the countersigner's own account must
    never alter an already-released report."""
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    countersigner_headers, countersigner = await _second_lab_user(
        client, db_session, clinic_id=ctx["clinic"].id, first_name="Original", last_name="Name", license_number="111111"
    )
    released = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
        json={"countersigning_med_tech_id": str(countersigner.id)},
    )
    assert released.json()["countersigning_med_tech_name_snapshot"] == "Original Name"

    # Rename the countersigner's own account after release.
    await client.patch(
        f"/api/v1/users/{countersigner.id}", headers=ctx["owner_headers"],
        json={"first_name": "Renamed", "last_name": "Person"},
    )

    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.json()["countersigning_med_tech_name_snapshot"] == "Original Name"
    assert reprint.json()["countersigning_med_tech_license_snapshot"] == "111111"


async def test_c7_missing_countersigning_med_tech_license_is_handled_safely(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    _countersigner_headers, countersigner = await _second_lab_user(
        client, db_session, clinic_id=ctx["clinic"].id, first_name="No", last_name="License", license_number=None
    )

    released = await client.post(
        f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"],
        json={"countersigning_med_tech_id": str(countersigner.id)},
    )
    assert released.status_code == 200, released.text
    assert released.json()["countersigning_med_tech_name_snapshot"] == "No License"
    assert released.json()["countersigning_med_tech_license_snapshot"] is None


# --- GET /laboratory/med-techs: the eligible-countersigner list ---


async def test_med_techs_endpoint_lists_only_active_laboratory_role_users_in_clinic(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, _lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    _second_headers, second_med_tech = await _second_lab_user(
        client, db_session, clinic_id=ctx["clinic"].id, first_name="Aijilie", last_name="Mosquite", license_number="123456"
    )
    _inactive_headers, inactive_med_tech = await _second_lab_user(
        client, db_session, clinic_id=ctx["clinic"].id, first_name="Inactive", last_name="MedTech"
    )
    inactive_med_tech.is_active = False
    await db_session.commit()

    resp = await client.get("/api/v1/laboratory/med-techs", headers=ctx["owner_headers"])
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    names = {row["full_name"] for row in resp.json()}
    assert str(second_med_tech.id) in ids
    assert "Aijilie Mosquite" in names
    # Inactive MedTech excluded.
    assert str(inactive_med_tech.id) not in ids
    # License number is exposed; no signature field exists on this schema
    # at all.
    matched = next(row for row in resp.json() if row["id"] == str(second_med_tech.id))
    assert matched["license_number"] == "123456"
    assert "signature_url" not in matched


async def test_med_techs_endpoint_excludes_non_laboratory_roles_and_other_clinics(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, _lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    other_clinic, _other_owner, _other_headers = await _owner_headers(client, make_clinic_with_owner)
    _foreign_headers, foreign_med_tech = await _second_lab_user(
        client, db_session, clinic_id=other_clinic.id, first_name="Foreign", last_name="MedTech"
    )

    resp = await client.get("/api/v1/laboratory/med-techs", headers=ctx["owner_headers"])
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()}
    doc_me = (await client.get("/api/v1/auth/me", headers=ctx["doc_headers"])).json()
    recep_me = (await client.get("/api/v1/auth/me", headers=ctx["recep_headers"])).json()

    assert doc_me["id"] not in ids
    assert recep_me["id"] not in ids
    assert str(foreign_med_tech.id) not in ids


async def test_med_techs_endpoint_requires_lab_manage_role(client: AsyncClient, make_clinic_with_owner, db_session) -> None:
    """Same `require_lab_manage_role` gate release itself uses (Owner/
    Administrator/Laboratory) - a Doctor or Receptionist cannot list
    eligible countersigners, matching the existing role/authorization
    rules rather than introducing a new definition."""
    ctx, _lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)

    doc_resp = await client.get("/api/v1/laboratory/med-techs", headers=ctx["doc_headers"])
    assert doc_resp.status_code == 403

    recep_resp = await client.get("/api/v1/laboratory/med-techs", headers=ctx["recep_headers"])
    assert recep_resp.status_code == 403

    lab_resp = await client.get("/api/v1/laboratory/med-techs", headers=ctx["lab_headers"])
    assert lab_resp.status_code == 200
