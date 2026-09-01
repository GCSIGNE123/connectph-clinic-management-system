"""Integration tests for per-doctor consultation workspace configuration:
show/hide + required toggles for consultation sections (vitals, diagnosis,
prescription, lab requests, medical certificate, attachments), presets, the
"no custom config = current behavior" default, and required-only-if-visible
enforcement at consultation completion - plus per-doctor SOAP field
visibility (`soap_fields`), the same JSONB `workspace_config` blob extended
with a flat {field_id: enabled} map. See `app/models/doctor.py`'s
`resolve_workspace_config`/`WORKSPACE_CONFIG_PRESETS`/`SOAP_FIELD_IDS` for
the data-driven source of truth these tests exercise.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.doctor import SOAP_FIELD_IDS, WORKSPACE_CONFIG_PRESETS
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
    doctor = (
        await client.post(
            "/api/v1/doctors", headers=headers,
            json={"first_name": "Jose", "last_name": "Rizal", "prc_license": "0123456", "ptr_number": "9876543"},
        )
    ).json()
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
                "first_name": "Juan", "last_name": "Dela Cruz", "birth_date": "1990-05-15",
                "gender": "Male", "civil_status": "Single", "mobile_number": "+639171234567",
            },
        )
    ).json()["patient"]
    return {
        "branch_id": branch["id"], "department_id": department["id"],
        "doctor_id": doctor["id"], "service_id": service["id"], "patient_id": patient["id"],
    }


def _queue_payload(deps: dict, **overrides) -> dict:
    payload = {
        "patient_id": deps["patient_id"], "branch_id": deps["branch_id"],
        "department_id": deps["department_id"], "doctor_id": deps["doctor_id"],
        "service_id": deps["service_id"], "priority": "Normal",
    }
    payload.update(overrides)
    return payload


async def _make_doctor_login(db_session: AsyncSession, *, clinic_id, doctor_id, password: str = "DoctorPass123!"):
    from app.models.user import User

    result = await db_session.execute(select(Role).where(Role.name == "Doctor"))
    doctor_role = result.scalar_one()
    suffix = uuid.uuid4().hex[:8]
    email = f"doc-{suffix}@example.com"
    user = User(
        clinic_id=clinic_id, email=email, username=f"doc{suffix}", hashed_password=hash_password(password),
        first_name="Test", last_name="Doctor", role_id=doctor_role.id, doctor_id=doctor_id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return email, user


async def _advance_to_in_consultation(client, doc_headers, visit_id) -> None:
    r1 = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/call", headers=doc_headers)
    assert r1.status_code == 200, r1.text
    r2 = await client.post(f"/api/v1/doctor-workspace/visits/{visit_id}/start-consultation", headers=doc_headers)
    assert r2.status_code == 200, r2.text


async def _setup_doctor_and_visit(client, make_clinic_with_owner, db_session):
    clinic, _owner, owner_headers = await _owner_headers(client, make_clinic_with_owner)
    deps = await _setup_queue_deps(client, owner_headers)
    queue = (await client.post("/api/v1/queues", headers=owner_headers, json=_queue_payload(deps))).json()
    visit_id = queue["visit_id"]

    doc_email, _doc_user = await _make_doctor_login(db_session, clinic_id=clinic.id, doctor_id=deps["doctor_id"])
    doc_token = await _login(client, doc_email, "DoctorPass123!")
    doc_headers = {"Authorization": f"Bearer {doc_token}"}
    await _advance_to_in_consultation(client, doc_headers, visit_id)
    return clinic, owner_headers, doc_headers, deps, visit_id


# --- Doctor CRUD surface: default + custom config + validation ---

async def test_doctor_with_no_custom_config_resolves_to_all_visible_not_required(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    fetched = await client.get(f"/api/v1/doctors/{doctor['id']}", headers=headers)
    assert fetched.status_code == 200
    config = fetched.json()["workspace_config"]
    assert set(config["sections"]) == {"vitals", "diagnosis", "prescription", "lab_requests", "certificate", "attachments"}
    assert all(s["visible"] is True and s["required"] is False for s in config["sections"].values())
    # SOAP fields default to fully enabled too - a doctor with no custom
    # config keeps the exact pre-feature SOAP workflow.
    assert set(config["soap_fields"]) == SOAP_FIELD_IDS
    assert all(enabled is True for enabled in config["soap_fields"].values())


async def test_update_doctor_workspace_config_persists_and_merges_partial_input(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    update = await client.put(
        f"/api/v1/doctors/{doctor['id']}", headers=headers,
        json={"workspace_config": {"sections": {"lab_requests": {"visible": False, "required": False}}}},
    )
    assert update.status_code == 200, update.text
    config = update.json()["workspace_config"]
    assert config["sections"]["lab_requests"]["visible"] is False
    # Every other section, untouched by the partial input, keeps its default.
    assert config["sections"]["vitals"]["visible"] is True
    assert config["sections"]["diagnosis"]["visible"] is True


async def test_update_doctor_workspace_config_rejects_unknown_section_id(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    update = await client.put(
        f"/api/v1/doctors/{doctor['id']}", headers=headers,
        json={"workspace_config": {"sections": {"not_a_real_section": {"visible": False}}}},
    )
    assert update.status_code == 422


async def test_required_but_not_visible_is_normalized_to_not_required(client: AsyncClient, make_clinic_with_owner) -> None:
    """'required flags are enforced only for visible sections' - stored as
    required+hidden, but the resolved config coming back must show
    required=False."""
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    update = await client.put(
        f"/api/v1/doctors/{doctor['id']}", headers=headers,
        json={"workspace_config": {"sections": {"diagnosis": {"visible": False, "required": True}}}},
    )
    assert update.status_code == 200, update.text
    assert update.json()["workspace_config"]["sections"]["diagnosis"] == {"visible": False, "required": False}


@pytest.mark.parametrize("preset_name", ["simple", "standard", "comprehensive"])
async def test_presets_apply_cleanly_via_the_existing_update_endpoint(
    client: AsyncClient, make_clinic_with_owner, preset_name: str
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    update = await client.put(
        f"/api/v1/doctors/{doctor['id']}", headers=headers,
        json={"workspace_config": WORKSPACE_CONFIG_PRESETS[preset_name]},
    )
    assert update.status_code == 200, update.text
    assert set(update.json()["workspace_config"]["sections"]) == set(WORKSPACE_CONFIG_PRESETS[preset_name]["sections"])


# --- Consultation detail exposes the resolved config ---

async def test_consultation_detail_exposes_doctor_workspace_config(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    await client.put(
        f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers,
        json={"workspace_config": {"sections": {"attachments": {"visible": False, "required": False}}}},
    )

    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    assert opened["doctor_workspace_config"]["sections"]["attachments"]["visible"] is False
    assert opened["doctor_workspace_config"]["sections"]["vitals"]["visible"] is True


# --- Required-only-if-visible enforcement at completion ---

async def test_complete_consultation_succeeds_with_default_config_and_no_extra_data(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """No custom config -> nothing required -> completing with just a bare
    consultation (no diagnosis/prescription/etc.) must still work, exactly
    like before this feature existed."""
    _clinic, _owner_headers, doc_headers, _deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    complete = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert complete.status_code == 200, complete.text


async def test_complete_consultation_blocks_when_required_visible_section_has_no_data(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    await client.put(
        f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers,
        json={"workspace_config": {"sections": {"diagnosis": {"visible": True, "required": True}}}},
    )
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    complete = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert complete.status_code == 400
    assert "Diagnosis" in complete.json()["detail"]


async def test_complete_consultation_succeeds_once_the_required_section_is_fulfilled(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    await client.put(
        f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers,
        json={"workspace_config": {"sections": {"diagnosis": {"visible": True, "required": True}}}},
    )
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    add = await client.post(
        f"/api/v1/consultations/{cid}/diagnoses", headers=doc_headers,
        json={"diagnosis_type": "Primary", "status": "Working", "notes": "Suspected flu"},
    )
    assert add.status_code == 200, add.text

    complete = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert complete.status_code == 200, complete.text


async def test_required_hidden_section_does_not_block_completion(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Stored as required+hidden - resolution strips `required`, so
    completing must succeed even though no lab request was ever created."""
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    await client.put(
        f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers,
        json={"workspace_config": {"sections": {"lab_requests": {"visible": False, "required": True}}}},
    )
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    complete = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert complete.status_code == 200, complete.text


async def test_comprehensive_preset_blocks_completion_until_all_required_sections_filled(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    await client.put(
        f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers,
        json={"workspace_config": WORKSPACE_CONFIG_PRESETS["comprehensive"]},
    )
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    blocked = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert blocked.status_code == 400
    detail = blocked.json()["detail"]
    assert "Vitals" in detail and "Diagnosis" in detail and "Prescription" in detail

    await client.put(f"/api/v1/consultations/{cid}/soap", headers=doc_headers, json={"height_cm": 170, "weight_kg": 65})
    await client.post(
        f"/api/v1/consultations/{cid}/diagnoses", headers=doc_headers,
        json={"diagnosis_type": "Primary", "status": "Working", "notes": "Hypertension"},
    )
    await client.post(
        f"/api/v1/consultations/{cid}/prescriptions", headers=doc_headers,
        json={"items": [{"medicine": "Amlodipine", "dosage": "5mg", "frequency": "Once daily"}]},
    )

    complete = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert complete.status_code == 200, complete.text


# --- Per-doctor SOAP field configuration ---

async def test_doctor_can_save_and_retrieve_soap_field_configuration(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    update = await client.put(
        f"/api/v1/doctors/{doctor['id']}", headers=headers,
        json={"workspace_config": {"soap_fields": {"family_history": False, "social_history": False}}},
    )
    assert update.status_code == 200, update.text
    saved = update.json()["workspace_config"]["soap_fields"]
    assert saved["family_history"] is False
    assert saved["social_history"] is False
    # Every other SOAP field, untouched by the partial input, keeps its
    # default-enabled state.
    assert saved["chief_complaint"] is True
    assert saved["referral_notes"] is True

    fetched = await client.get(f"/api/v1/doctors/{doctor['id']}", headers=headers)
    assert fetched.status_code == 200
    refetched = fetched.json()["workspace_config"]["soap_fields"]
    assert refetched["family_history"] is False
    assert refetched["social_history"] is False
    assert refetched["chief_complaint"] is True


async def test_soap_field_configuration_is_doctor_specific(client: AsyncClient, make_clinic_with_owner) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor_a = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Doctor", "last_name": "A"})
    ).json()
    doctor_b = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "Doctor", "last_name": "B"})
    ).json()

    await client.put(
        f"/api/v1/doctors/{doctor_a['id']}", headers=headers,
        json={"workspace_config": {"soap_fields": {"differential_diagnosis": False, "referral_notes": False}}},
    )

    config_a = (await client.get(f"/api/v1/doctors/{doctor_a['id']}", headers=headers)).json()["workspace_config"]
    config_b = (await client.get(f"/api/v1/doctors/{doctor_b['id']}", headers=headers)).json()["workspace_config"]

    assert config_a["soap_fields"]["differential_diagnosis"] is False
    assert config_a["soap_fields"]["referral_notes"] is False
    # Doctor B was never touched - still every field enabled.
    assert config_b["soap_fields"]["differential_diagnosis"] is True
    assert config_b["soap_fields"]["referral_notes"] is True


async def test_update_doctor_soap_field_configuration_rejects_unknown_field_id(
    client: AsyncClient, make_clinic_with_owner
) -> None:
    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    update = await client.put(
        f"/api/v1/doctors/{doctor['id']}", headers=headers,
        json={"workspace_config": {"soap_fields": {"not_a_real_field": False}}},
    )
    assert update.status_code == 422


async def test_soap_fields_missing_from_stored_config_safely_fall_back_to_enabled(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """A doctor's `workspace_config` saved before `soap_fields` existed (or
    with only `sections` ever written) has no `soap_fields` key at all in
    the stored JSONB - `resolve_workspace_config` must still return every
    SOAP field enabled, never null/missing/crash."""
    from app.models.doctor import Doctor

    _clinic, _owner, headers = await _owner_headers(client, make_clinic_with_owner)
    doctor_resp = (
        await client.post("/api/v1/doctors", headers=headers, json={"first_name": "New", "last_name": "Doctor"})
    ).json()

    doctor = await db_session.get(Doctor, uuid.UUID(doctor_resp["id"]))
    doctor.workspace_config = {"sections": {"attachments": {"visible": False, "required": False}}}
    await db_session.commit()

    fetched = await client.get(f"/api/v1/doctors/{doctor_resp['id']}", headers=headers)
    assert fetched.status_code == 200
    config = fetched.json()["workspace_config"]
    assert config["sections"]["attachments"]["visible"] is False
    assert set(config["soap_fields"]) == SOAP_FIELD_IDS
    assert all(enabled is True for enabled in config["soap_fields"].values())


async def test_soap_field_configuration_is_exposed_on_consultation_detail(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    await client.put(
        f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers,
        json={"workspace_config": {"soap_fields": {"family_history": False}}},
    )

    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    assert opened["doctor_workspace_config"]["soap_fields"]["family_history"] is False
    assert opened["doctor_workspace_config"]["soap_fields"]["chief_complaint"] is True


async def test_disabling_a_soap_field_does_not_delete_previously_saved_data(
    client: AsyncClient, make_clinic_with_owner, db_session
) -> None:
    """Disabling a SOAP field is a display-only concern - it must never
    clear/destroy data already saved in that field on an existing
    consultation's SOAP note."""
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    opened = (await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)).json()
    cid = opened["id"]

    saved = await client.put(
        f"/api/v1/consultations/{cid}/soap", headers=doc_headers,
        json={"family_history": "Father: Type 2 Diabetes", "referral_notes": "Refer to Cardiology"},
    )
    assert saved.status_code == 200, saved.text

    # Now the doctor disables Family history and Referral notes going forward.
    await client.put(
        f"/api/v1/doctors/{deps['doctor_id']}", headers=owner_headers,
        json={"workspace_config": {"soap_fields": {"family_history": False, "referral_notes": False}}},
    )

    refetched = await client.get(f"/api/v1/consultations/{cid}", headers=doc_headers)
    assert refetched.status_code == 200, refetched.text
    soap = refetched.json()["soap_note"]
    # Data survives untouched even though the field is now hidden by config.
    assert soap["family_history"] == "Father: Type 2 Diabetes"
    assert soap["referral_notes"] == "Refer to Cardiology"
    assert refetched.json()["doctor_workspace_config"]["soap_fields"]["family_history"] is False
