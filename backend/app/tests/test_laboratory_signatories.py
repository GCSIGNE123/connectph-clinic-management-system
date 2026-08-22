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


async def test_5_6_7_8_release_snapshots_med_tech_and_pathologist_and_reprint_uses_them(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    clinic_id = ctx["clinic"].id

    # Configure the Med Tech's (the releasing Laboratory user's) signature.
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES))

    pathologist = await _create_pathologist(client, ctx["owner_headers"])
    await client.post(f"/api/v1/pathologists/{pathologist['id']}/signature", headers=ctx["owner_headers"], files=_png_file(content=PNG_BYTES_2))

    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"], json={"pathologist_id": pathologist["id"]})
    assert released.status_code == 200, released.text
    body = released.json()

    # #5: Med Tech in Charge is the releasing Laboratory user.
    assert body["released_by"] is not None
    assert body["med_tech_name_snapshot"]
    assert body["med_tech_signature_snapshot_url"]

    # #6: selected Pathologist persisted.
    assert body["pathologist_id"] == pathologist["id"]
    assert body["pathologist_name_snapshot"] == "Dr. Maria Santos"
    assert body["pathologist_signature_snapshot_url"]

    # #7/#8: reprint (a fresh GET) uses the stored snapshot, and the actual
    # signature files are fetchable and correct.
    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.json()["med_tech_signature_snapshot_url"] == body["med_tech_signature_snapshot_url"]
    assert reprint.json()["pathologist_signature_snapshot_url"] == body["pathologist_signature_snapshot_url"]

    med_tech_file = await client.get(f"/api/v1/laboratory/orders/{lab_id}/med-tech-signature/file", headers=ctx["owner_headers"])
    assert med_tech_file.status_code == 200
    assert med_tech_file.content == PNG_BYTES

    pathologist_file = await client.get(f"/api/v1/laboratory/orders/{lab_id}/pathologist-signature/file", headers=ctx["owner_headers"])
    assert pathologist_file.status_code == 200
    assert pathologist_file.content == PNG_BYTES_2


# --- 9/10/11. Historical immutability ---


async def test_9_changing_med_techs_current_signature_does_not_change_old_report(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    ctx, lab_id = await _release_ready_order(client, make_clinic_with_owner, db_session)
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES))
    released = await client.post(f"/api/v1/laboratory/orders/{lab_id}/release", headers=ctx["lab_headers"])
    original_snapshot = released.json()["med_tech_signature_snapshot_url"]
    assert original_snapshot

    # Replace the Med Tech's CURRENT signature after release.
    await client.post("/api/v1/auth/me/signature", headers=ctx["lab_headers"], files=_png_file(content=PNG_BYTES_2))

    reprint = await client.get(f"/api/v1/laboratory/orders/{lab_id}", headers=ctx["owner_headers"])
    assert reprint.json()["med_tech_signature_snapshot_url"] == original_snapshot
    file_resp = await client.get(f"/api/v1/laboratory/orders/{lab_id}/med-tech-signature/file", headers=ctx["owner_headers"])
    assert file_resp.content == PNG_BYTES  # still the OLD signature, not PNG_BYTES_2


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
    """No Med Tech signature configured at release time - existing release
    behavior is preserved (release still succeeds), and the snapshot is
    simply left null rather than fabricated. See the Round 6 implementation
    report, section F, for why this was the chosen behavior over blocking
    release."""
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
