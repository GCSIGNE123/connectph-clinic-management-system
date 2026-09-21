"""Task #6: Receptionist / Nurse SOAP pre-entry.

Reception and Nurse may write ONLY the approved Subjective + vitals fields through
`PUT /consultations/{id}/soap/subjective-objective`: unsupported keys are a 422 (never
silently dropped), Doctor-only fields (physical examination, clinical findings, all
Assessment/Plan) are unreachable, saves are partial merges that never wipe Doctor-entered
data, signed consultations stay locked, and everything is clinic-scoped. The Task #2
suggestion endpoint is open to them for `chief_complaint` only.
"""

import pytest
from httpx import AsyncClient

from app.tests.test_billing import _login, _make_role_login
from app.tests.test_consultations import _setup_doctor_and_visit

pytestmark = pytest.mark.asyncio

SO = "/api/v1/consultations/{cid}/soap/subjective-objective"
SOAP = "/api/v1/consultations/{cid}/soap"
SUGGEST = "/api/v1/consultations/soap-suggestions"

APPROVED_SUBJECTIVE = {
    "chief_complaint": "Cough for 3 days",
    "history_of_present_illness": "Started 3 days ago, worse at night",
    "past_medical_history": "Asthma",
    "family_history": "Hypertension (father)",
    "social_history": "Non-smoker",
    "review_of_systems": "No chest pain",
    "subjective_notes": "Reception intake note",
}
APPROVED_VITALS = {
    "blood_pressure": "120/80", "pulse_rate": 76, "respiratory_rate": 18, "temperature": 36.9,
    "height_cm": 170.0, "weight_kg": 68.0, "oxygen_saturation": 98.0, "pain_score": 3, "head_circumference_cm": 54.5,
}
DOCTOR_ONLY = {
    "physical_examination": "x", "clinical_findings": "x", "clinical_impression": "x", "differential_diagnosis": "x",
    "assessment_notes": "x", "treatment_plan": "x", "patient_instructions": "x", "followup_recommendation": "x",
    "referral_notes": "x",
}


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


async def _role_headers(client, db_session, clinic, role: str) -> dict:
    email, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name=role)
    return {"Authorization": f"Bearer {await _login(client, email, 'TestPass123!')}"}


async def _open(client, doc_headers, visit_id) -> str:
    resp = await client.post(f"/api/v1/visits/{visit_id}/consultation/open", headers=doc_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _setup(client, make_clinic_with_owner, db_session):
    clinic, owner_headers, doc_headers, deps, visit_id = await _setup_doctor_and_visit(client, make_clinic_with_owner, db_session)
    cid = await _open(client, doc_headers, visit_id)
    return clinic, owner_headers, doc_headers, deps, visit_id, cid


async def _soap(client, headers, cid) -> dict:
    resp = await client.get(SOAP.format(cid=cid), headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- allowed fields ---------------------------------------------------------


@pytest.mark.parametrize("role", ["Receptionist", "Nurse"])
async def test_reception_and_nurse_can_save_all_approved_subjective_fields(client, make_clinic_with_owner, db_session, role) -> None:
    clinic, _o, doc_headers, _d, visit_id, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, role)
    resp = await client.put(SO.format(cid=cid), headers=headers, json=APPROVED_SUBJECTIVE)
    assert resp.status_code == 200, resp.text
    saved = resp.json()["soap_note"]
    for key, value in APPROVED_SUBJECTIVE.items():
        assert saved[key] == value


@pytest.mark.parametrize("role", ["Receptionist", "Nurse"])
async def test_reception_and_nurse_can_save_all_approved_vitals_and_bmi_is_server_computed(client, make_clinic_with_owner, db_session, role) -> None:
    clinic, _o, _doc, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, role)
    resp = await client.put(SO.format(cid=cid), headers=headers, json=APPROVED_VITALS)
    assert resp.status_code == 200, resp.text
    saved = resp.json()["soap_note"]
    for key, value in APPROVED_VITALS.items():
        assert saved[key] == value
    assert saved["bmi"] == pytest.approx(23.53, abs=0.01)  # 68 / 1.7^2, computed server-side


async def test_chief_complaint_alone_saves(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, _doc, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    resp = await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "Fever"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["soap_note"]["chief_complaint"] == "Fever"


# --- forbidden / unsupported fields -> 422, never silently dropped --------------


@pytest.mark.parametrize("role", ["Receptionist", "Nurse"])
@pytest.mark.parametrize("field", sorted(DOCTOR_ONLY))
async def test_doctor_only_fields_are_rejected_with_422_and_nothing_is_written(
    client, make_clinic_with_owner, db_session, role, field
) -> None:
    clinic, _o, doc_headers, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, role)
    resp = await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "Cough", field: "Injected by reception"})
    assert resp.status_code == 422, (field, resp.text)
    assert field in resp.text  # the validation error names the offending key
    # Nothing was written - not even the allowed field submitted in the same request.
    body = (await client.get(SOAP.format(cid=cid), headers=doc_headers)).json()
    assert not body or (body.get(field) in (None, "") and body.get("chief_complaint") in (None, ""))


async def test_unknown_keys_are_a_422(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, _doc, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    for payload in ({"bogus_field": "x"}, {"id": "x"}, {"clinic_id": "x"}, {"bmi": 99}):
        resp = await client.put(SO.format(cid=cid), headers=headers, json=payload)
        assert resp.status_code == 422, (payload, resp.text)


async def test_the_read_endpoint_never_exposes_doctor_only_fields(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, doc_headers, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    await client.put(SOAP.format(cid=cid), headers=doc_headers, json={"treatment_plan": "Secret plan", "physical_examination": "PE text", "chief_complaint": "Cough"})
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    resp = await client.get(SO.format(cid=cid), headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["chief_complaint"] == "Cough"
    for key in DOCTOR_ONLY:
        assert key not in body


# --- merge / handoff ---------------------------------------------------------


async def test_reception_save_does_not_wipe_doctor_entered_assessment_plan_or_other_fields(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, doc_headers, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    doctor_fields = {
        "history_of_present_illness": "Doctor HPI", "physical_examination": "Doctor PE", "clinical_findings": "Doctor findings",
        "clinical_impression": "Viral URI", "differential_diagnosis": "Bacterial", "assessment_notes": "Doctor notes",
        "treatment_plan": "Rest and fluids", "patient_instructions": "Return in 3 days", "followup_recommendation": "1 week",
        "referral_notes": "None", "temperature": 37.2,
    }
    assert (await client.put(SOAP.format(cid=cid), headers=doc_headers, json=doctor_fields)).status_code == 200

    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    resp = await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "Reception chief complaint", "pulse_rate": 80})
    assert resp.status_code == 200, resp.text

    after = await _soap(client, doc_headers, cid)
    for key, value in doctor_fields.items():
        assert after[key] == value, key  # every field the reception save did not submit is untouched
    assert after["chief_complaint"] == "Reception chief complaint" and after["pulse_rate"] == 80


async def test_an_explicit_null_clears_only_that_field(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, doc_headers, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "Cough", "family_history": "HTN"})
    resp = await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": None})
    assert resp.status_code == 200
    after = await _soap(client, doc_headers, cid)
    assert after["chief_complaint"] is None and after["family_history"] == "HTN"


async def test_doctor_can_read_and_continue_editing_reception_entered_data(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, doc_headers, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, "Nurse")
    await client.put(SO.format(cid=cid), headers=headers, json={**APPROVED_SUBJECTIVE, **APPROVED_VITALS})

    seen = await _soap(client, doc_headers, cid)
    assert seen["chief_complaint"] == APPROVED_SUBJECTIVE["chief_complaint"] and seen["pulse_rate"] == 76
    edited = await client.put(SOAP.format(cid=cid), headers=doc_headers, json={"chief_complaint": "Doctor refined complaint", "treatment_plan": "Plan"})
    assert edited.status_code == 200, edited.text
    final = await _soap(client, doc_headers, cid)
    assert final["chief_complaint"] == "Doctor refined complaint" and final["treatment_plan"] == "Plan"
    assert final["history_of_present_illness"] == APPROVED_SUBJECTIVE["history_of_present_illness"]  # reception data kept


async def test_reception_never_needs_the_doctor_lock_and_does_not_disturb_it(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, doc_headers, _d, visit_id, cid = await _setup(client, make_clinic_with_owner, db_session)  # doctor holds the lock
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    opened = await client.post(f"/api/v1/visits/{visit_id}/consultation/open-for-reception", headers=headers)
    assert opened.status_code == 200, opened.text
    assert (await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "While doctor has it open"})).status_code == 200
    # the doctor can keep saving afterwards
    assert (await client.put(SOAP.format(cid=cid), headers=doc_headers, json={"treatment_plan": "Doctor still edits"})).status_code == 200


async def test_administrator_and_owner_keep_their_existing_access_to_the_so_endpoint(client, make_clinic_with_owner, db_session) -> None:
    clinic, owner_headers, _doc, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    admin = await _role_headers(client, db_session, clinic, "Administrator")
    for headers in (admin, owner_headers):
        assert (await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "By admin/owner"})).status_code == 200
        assert (await client.put(SO.format(cid=cid), headers=headers, json={"treatment_plan": "x"})).status_code == 422  # still no Plan here


# --- signed, tenant, roles ----------------------------------------------------


async def test_signed_consultation_cannot_be_edited_by_reception(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, doc_headers, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "Before signing"})
    done = await client.post(f"/api/v1/consultations/{cid}/complete", headers=doc_headers)
    assert done.status_code == 200, done.text
    if done.json()["status"] != "Signed":  # committed behavior completes straight to Signed; sign explicitly if not
        assert (await client.post(f"/api/v1/consultations/{cid}/sign", headers=doc_headers)).status_code == 200
    resp = await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "After signing"})
    assert resp.status_code == 400 and "signed" in resp.text.lower()
    assert (await _soap(client, doc_headers, cid))["chief_complaint"] == "Before signing"


async def test_reception_cannot_complete_or_sign(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, _doc, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    for path in ("complete", "sign"):
        assert (await client.post(f"/api/v1/consultations/{cid}/{path}", headers=headers)).status_code == 403


async def test_reception_cannot_use_the_full_doctor_soap_endpoints(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, _doc, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, "Receptionist")
    assert (await client.get(SOAP.format(cid=cid), headers=headers)).status_code == 403
    assert (await client.put(SOAP.format(cid=cid), headers=headers, json={"treatment_plan": "x"})).status_code == 403


async def test_another_clinics_consultation_is_not_accessible(client, make_clinic_with_owner, db_session) -> None:
    clinic_a, _oa, doc_a, _da, _va, cid_a = await _setup(client, make_clinic_with_owner, db_session)
    clinic_b, _ob, _docb, _db, _vb, _cidb = await _setup(client, make_clinic_with_owner, db_session)
    await client.put(SOAP.format(cid=cid_a), headers=doc_a, json={"chief_complaint": "Clinic A private"})
    reception_b = await _role_headers(client, db_session, clinic_b, "Receptionist")
    assert (await client.get(SO.format(cid=cid_a), headers=reception_b)).status_code == 404
    assert (await client.put(SO.format(cid=cid_a), headers=reception_b, json={"chief_complaint": "Cross-clinic write"})).status_code == 404
    assert (await _soap(client, doc_a, cid_a))["chief_complaint"] == "Clinic A private"


@pytest.mark.parametrize("role", ["Cashier", "Laboratory", "Pharmacy", "Viewer"])
async def test_other_roles_are_rejected_on_the_so_endpoints(client, make_clinic_with_owner, db_session, role) -> None:
    clinic, _o, _doc, _d, visit_id, cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, role)
    assert (await client.get(SO.format(cid=cid), headers=headers)).status_code == 403
    assert (await client.put(SO.format(cid=cid), headers=headers, json={"chief_complaint": "x"})).status_code == 403
    assert (await client.post(f"/api/v1/visits/{visit_id}/consultation/open-for-reception", headers=headers)).status_code == 403


async def test_unauthenticated_is_rejected(client, make_clinic_with_owner, db_session) -> None:
    _c, _o, _doc, _d, _v, cid = await _setup(client, make_clinic_with_owner, db_session)
    assert (await client.put(SO.format(cid=cid), json={"chief_complaint": "x"})).status_code in (401, 403)


# --- Task #2 suggestions for reception/nurse ------------------------------------


@pytest.mark.parametrize("role", ["Receptionist", "Nurse"])
async def test_reception_and_nurse_may_request_only_in_scope_suggestions(client, make_clinic_with_owner, db_session, role) -> None:
    clinic, _o, _doc, _d, _v, _cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, role)
    ok = await client.get(SUGGEST, headers=headers, params={"field": "chief_complaint"})
    assert ok.status_code == 200 and set(ok.json()) == {"field", "suggestions"}


@pytest.mark.parametrize("role", ["Receptionist", "Nurse"])
@pytest.mark.parametrize(
    "field",
    ["physical_examination", "clinical_findings", "clinical_impression", "differential_diagnosis", "treatment_plan",
     "patient_instructions", "followup_recommendation", "icd10_code", "icd10_description"],
)
async def test_doctor_only_suggestion_fields_are_403_for_reception_and_nurse(client, make_clinic_with_owner, db_session, role, field) -> None:
    clinic, _o, _doc, _d, _v, _cid = await _setup(client, make_clinic_with_owner, db_session)
    headers = await _role_headers(client, db_session, clinic, role)
    assert (await client.get(SUGGEST, headers=headers, params={"field": field})).status_code == 403


async def test_reception_suggestions_for_non_allowlisted_fields_are_422_and_doctor_access_is_unchanged(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, doc_headers, _d, _v, _cid = await _setup(client, make_clinic_with_owner, db_session)
    reception = await _role_headers(client, db_session, clinic, "Receptionist")
    assert (await client.get(SUGGEST, headers=reception, params={"field": "history_of_present_illness"})).status_code == 422
    for field in ("chief_complaint", "physical_examination", "clinical_impression", "treatment_plan", "icd10_code"):
        assert (await client.get(SUGGEST, headers=doc_headers, params={"field": field})).status_code == 200


async def test_other_roles_still_get_403_on_suggestions(client, make_clinic_with_owner, db_session) -> None:
    clinic, _o, _doc, _d, _v, _cid = await _setup(client, make_clinic_with_owner, db_session)
    for role in ("Cashier", "Laboratory"):
        headers = await _role_headers(client, db_session, clinic, role)
        assert (await client.get(SUGGEST, headers=headers, params={"field": "chief_complaint"})).status_code == 403
