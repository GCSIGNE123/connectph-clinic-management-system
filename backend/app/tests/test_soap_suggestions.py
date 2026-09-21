"""Task #2: clinic-learned SOAP / diagnosis suggestions.

`GET /consultations/soap-suggestions?field=&q=` is read-only, clinic-scoped and
gated to Doctor/Owner/Administrator. A value only becomes a suggestion when it
was used in consultations of at least 2 DIFFERENT patients, is short, and is not
obviously identifying/junk. It returns suggestion text only.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.consultation import Consultation
from app.models.diagnosis import Diagnosis, DiagnosisType
from app.models.soap_note import SoapNote
from app.models.visit import Visit
from app.services.soap_suggestion_service import is_suggestible
from app.tests.test_billing import _login, _make_role_login, _setup_queue_deps

pytestmark = pytest.mark.asyncio

URL = "/api/v1/consultations/soap-suggestions"


@pytest.fixture(autouse=True)
def _reset_login_rate_limit():
    from app.core.rate_limit import _memory_buckets

    _memory_buckets.clear()
    yield
    _memory_buckets.clear()


_seq = {"n": 0}


def _n() -> int:
    _seq["n"] += 1
    return _seq["n"]


async def _setup_clinic(client: AsyncClient, make_clinic_with_owner):
    clinic, owner, password = await make_clinic_with_owner()
    headers = {"Authorization": f"Bearer {await _login(client, owner.email, password)}"}
    deps = await _setup_queue_deps(client, headers)
    return clinic, headers, deps


async def _patient(client: AsyncClient, headers) -> str:
    n = _n()
    resp = await client.post(
        "/api/v1/patients",
        headers=headers,
        json={
            "first_name": f"Sug{n}", "last_name": "Patient", "birth_date": f"19{60 + n % 30}-01-15",
            "gender": "Male", "civil_status": "Single", "mobile_number": f"+63918{n:07d}",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["patient"]["id"]


async def _consultation(db, clinic, deps, patient_id: str, *, soap: dict | None = None, diagnoses: list[dict] | None = None):
    """One visit + consultation (+ SOAP note / diagnoses) written straight through the ORM."""
    n = _n()
    visit = Visit(
        clinic_id=clinic.id, branch_id=uuid.UUID(deps["branch_id"]), patient_id=uuid.UUID(patient_id),
        visit_number=f"VIS-S-{n:06d}", visit_date=datetime.now(UTC).date(),
    )
    db.add(visit)
    await db.flush()
    consultation = Consultation(
        clinic_id=clinic.id, visit_id=visit.id, branch_id=uuid.UUID(deps["branch_id"]),
        doctor_id=uuid.UUID(deps["doctor_id"]), patient_id=uuid.UUID(patient_id), started_at=datetime.now(UTC),
    )
    db.add(consultation)
    await db.flush()
    if soap is not None:
        db.add(SoapNote(clinic_id=clinic.id, consultation_id=consultation.id, **soap))
    for d in diagnoses or []:
        db.add(Diagnosis(clinic_id=clinic.id, consultation_id=consultation.id, diagnosis_type=DiagnosisType.PRIMARY, **d))
    await db.commit()
    return consultation


async def _suggest(client, headers, field: str, **params) -> list[str]:
    resp = await client.get(URL, headers=headers, params={"field": field, **params})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["field"] == field
    return [s["text"] for s in body["suggestions"]]


async def _two_patients_use(db, client, headers, clinic, deps, field: str, value_a: str, value_b: str | None = None):
    for value in (value_a, value_b or value_a):
        pid = await _patient(client, headers)
        await _consultation(db, clinic, deps, pid, soap={field: value})


# --- Threshold: 2 DIFFERENT patients ---------------------------------------


async def test_two_different_patients_satisfy_the_threshold(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    await _two_patients_use(db_session, client, headers, clinic, deps, "chief_complaint", "Headache")
    assert await _suggest(client, headers, "chief_complaint") == ["Headache"]


async def test_same_patient_duplicates_do_not_satisfy_the_threshold(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    pid = await _patient(client, headers)
    for _ in range(3):  # three consultations, ONE patient
        await _consultation(db_session, clinic, deps, pid, soap={"chief_complaint": "Vertigo"})
    assert await _suggest(client, headers, "chief_complaint") == []
    # one more, different patient -> now it qualifies
    other = await _patient(client, headers)
    await _consultation(db_session, clinic, deps, other, soap={"chief_complaint": "Vertigo"})
    assert await _suggest(client, headers, "chief_complaint") == ["Vertigo"]


async def test_single_patient_value_is_never_suggested(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    await _consultation(db_session, clinic, deps, await _patient(client, headers), soap={"chief_complaint": "Rare private complaint"})
    assert await _suggest(client, headers, "chief_complaint") == []


# --- Normalization / dedupe / length / junk --------------------------------


async def test_case_insensitive_duplicates_collapse_and_whitespace_is_normalized(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    for value in ("Headache", "headache", "  HEADACHE  ", "Head   ache"):  # last one is a different phrase
        await _consultation(db_session, clinic, deps, await _patient(client, headers), soap={"chief_complaint": value})
    for value in ("Sore   throat", "sore throat"):
        await _consultation(db_session, clinic, deps, await _patient(client, headers), soap={"chief_complaint": value})

    got = await _suggest(client, headers, "chief_complaint")
    assert [g.lower() for g in got].count("headache") == 1
    assert got[0].lower() == "headache"  # 3 patients beats the others
    assert [g for g in got if g.lower() == "sore throat"] and "  " not in "".join(got)  # collapsed + single spaces


async def test_short_value_limit_is_enforced(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    long_value = "x" * 40 + " " + "y" * 45  # 86 chars after normalization
    ok_value = "Persistent dry cough"
    await _two_patients_use(db_session, client, headers, clinic, deps, "chief_complaint", long_value)
    await _two_patients_use(db_session, client, headers, clinic, deps, "chief_complaint", ok_value)
    assert await _suggest(client, headers, "chief_complaint") == [ok_value]


async def test_multiline_values_are_not_suggested(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    await _two_patients_use(db_session, client, headers, clinic, deps, "treatment_plan", "Rest\nFluids")
    assert await _suggest(client, headers, "treatment_plan") == []


@pytest.mark.parametrize(
    "junk",
    ["reach me at juan@example.com", "see https://example.com/x", "www.clinic.ph", "call 0917 123 4567", "+63 917 123 4567",
     "PAT-000086", "VIS-20260920-000004", "asdf", "Test plan", "regression verification test",
     "3fa85f64-5717-4562-b3fc-2c963f66afa6", "abcdefghij123"],
)
async def test_obvious_identifying_or_junk_values_are_excluded(client, make_clinic_with_owner, db_session, junk) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    await _two_patients_use(db_session, client, headers, clinic, deps, "clinical_impression", junk)
    await _two_patients_use(db_session, client, headers, clinic, deps, "clinical_impression", "Viral URI")
    assert await _suggest(client, headers, "clinical_impression") == ["Viral URI"]


def test_junk_filter_keeps_normal_clinical_phrases_and_icd_codes() -> None:
    for ok in ("Fever and cough for 3 days", "Repeat blood test in 1 week", "Rest, hydration, paracetamol", "Upper abdominal pain"):
        assert is_suggestible(ok, "treatment_plan"), ok
    assert is_suggestible("J06.9", "icd10_code")
    assert is_suggestible("Acute upper respiratory infection, unspecified", "icd10_description")
    assert not is_suggestible("0917-123-4567", "icd10_description")


# --- Query, ordering, limit -------------------------------------------------


async def test_query_filtering_and_case_insensitive_match(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    for value in ("Fever", "Cough", "Cough and colds"):
        await _two_patients_use(db_session, client, headers, clinic, deps, "chief_complaint", value)
    assert sorted(await _suggest(client, headers, "chief_complaint", q="COUGH")) == ["Cough", "Cough and colds"]
    assert await _suggest(client, headers, "chief_complaint", q="zzz") == []
    # SQL wildcard characters in q are literal, not patterns.
    assert await _suggest(client, headers, "chief_complaint", q="%") == []
    assert await _suggest(client, headers, "chief_complaint", q="_") == []


async def test_ordering_is_most_patients_first_then_alphabetical_and_deterministic(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    for value, patients in (("Zeta pain", 2), ("Alpha pain", 2), ("Beta pain", 3)):
        for _ in range(patients):
            await _consultation(db_session, clinic, deps, await _patient(client, headers), soap={"chief_complaint": value})
    first = await _suggest(client, headers, "chief_complaint")
    assert first == ["Beta pain", "Alpha pain", "Zeta pain"]  # 3 patients, then the 2-patient ties A-Z
    assert await _suggest(client, headers, "chief_complaint") == first


async def test_limit_is_bounded(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    for i in range(6):
        await _two_patients_use(db_session, client, headers, clinic, deps, "chief_complaint", f"Complaint {chr(65 + i)}")
    assert len(await _suggest(client, headers, "chief_complaint", limit=3)) == 3
    assert (await client.get(URL, headers=headers, params={"field": "chief_complaint", "limit": 99})).status_code == 422


# --- Fields, diagnoses, isolation, privacy, roles ---------------------------


@pytest.mark.parametrize(
    "field",
    ["chief_complaint", "physical_examination", "clinical_findings", "clinical_impression", "differential_diagnosis",
     "treatment_plan", "patient_instructions", "followup_recommendation"],
)
async def test_every_approved_soap_field_is_supported(client, make_clinic_with_owner, db_session, field) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    await _two_patients_use(db_session, client, headers, clinic, deps, field, "Common phrase")
    assert await _suggest(client, headers, field) == ["Common phrase"]


@pytest.mark.parametrize(
    "field",
    ["history_of_present_illness", "past_medical_history", "family_history", "social_history", "review_of_systems",
     "subjective_notes", "assessment_notes", "referral_notes", "bmi", "id", "clinic_id", "hashed_password", "consultation_id", ""],
)
async def test_unsupported_fields_and_arbitrary_columns_are_rejected(client, make_clinic_with_owner, field) -> None:
    _clinic, headers, _deps = await _setup_clinic(client, make_clinic_with_owner)
    resp = await client.get(URL, headers=headers, params={"field": field})
    assert resp.status_code == 422, (field, resp.text)


async def test_missing_field_param_is_rejected(client, make_clinic_with_owner) -> None:
    _clinic, headers, _deps = await _setup_clinic(client, make_clinic_with_owner)
    assert (await client.get(URL, headers=headers)).status_code == 422


async def test_diagnosis_code_and_description_learned_from_clinic_diagnoses(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    for _ in range(2):
        await _consultation(
            db_session, clinic, deps, await _patient(client, headers),
            diagnoses=[{"icd10_code": "J06.9", "icd10_description": "Acute upper respiratory infection, unspecified"}],
        )
    await _consultation(db_session, clinic, deps, await _patient(client, headers), diagnoses=[{"icd10_code": "Z99.9", "icd10_description": "One-off"}])
    assert await _suggest(client, headers, "icd10_code") == ["J06.9"]
    assert await _suggest(client, headers, "icd10_description", q="respiratory") == ["Acute upper respiratory infection, unspecified"]
    assert await _suggest(client, headers, "icd10_description", q="one-off") == []


async def test_suggestions_are_tenant_isolated(client, make_clinic_with_owner, db_session) -> None:
    clinic_a, headers_a, deps_a = await _setup_clinic(client, make_clinic_with_owner)
    _clinic_b, headers_b, _deps_b = await _setup_clinic(client, make_clinic_with_owner)
    await _two_patients_use(db_session, client, headers_a, clinic_a, deps_a, "chief_complaint", "Clinic A only complaint")
    assert await _suggest(client, headers_a, "chief_complaint") == ["Clinic A only complaint"]
    assert await _suggest(client, headers_b, "chief_complaint") == []
    assert await _suggest(client, headers_b, "chief_complaint", q="clinic a") == []


async def test_a_value_split_across_two_clinics_never_qualifies(client, make_clinic_with_owner, db_session) -> None:
    """One patient in clinic A and one in clinic B using the same phrase must not add up to 2 patients."""
    clinic_a, headers_a, deps_a = await _setup_clinic(client, make_clinic_with_owner)
    clinic_b, headers_b, deps_b = await _setup_clinic(client, make_clinic_with_owner)
    await _consultation(db_session, clinic_a, deps_a, await _patient(client, headers_a), soap={"chief_complaint": "Shared phrase"})
    await _consultation(db_session, clinic_b, deps_b, await _patient(client, headers_b), soap={"chief_complaint": "Shared phrase"})
    assert await _suggest(client, headers_a, "chief_complaint") == []
    assert await _suggest(client, headers_b, "chief_complaint") == []


async def test_response_contains_text_only_no_identifiers(client, make_clinic_with_owner, db_session) -> None:
    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    await _two_patients_use(db_session, client, headers, clinic, deps, "chief_complaint", "Headache")
    resp = await client.get(URL, headers=headers, params={"field": "chief_complaint"})
    body = resp.json()
    assert set(body) == {"field", "suggestions"}
    assert body["suggestions"] == [{"text": "Headache"}]
    raw = resp.text
    for marker in ("patient_id", "consultation_id", "visit_id", "Sug", "count"):
        assert marker not in raw


async def test_role_gating(client, make_clinic_with_owner, db_session) -> None:
    clinic, _headers, _deps = await _setup_clinic(client, make_clinic_with_owner)
    # Task #6: Receptionist/Nurse may request the in-scope field (chief_complaint) only - see test_reception_soap.py.
    for role, expected in (("Doctor", 200), ("Administrator", 200), ("Receptionist", 200), ("Nurse", 200), ("Cashier", 403), ("Laboratory", 403)):
        email, _user = await _make_role_login(db_session, clinic_id=clinic.id, role_name=role)
        token = await _login(client, email, "TestPass123!")
        resp = await client.get(URL, headers={"Authorization": f"Bearer {token}"}, params={"field": "chief_complaint"})
        assert resp.status_code == expected, (role, resp.text)
    assert (await client.get(URL, params={"field": "chief_complaint"})).status_code in (401, 403)


async def test_route_is_not_swallowed_by_the_consultation_id_route(client, make_clinic_with_owner) -> None:
    _clinic, headers, _deps = await _setup_clinic(client, make_clinic_with_owner)
    resp = await client.get(URL, headers=headers, params={"field": "chief_complaint"})
    assert resp.status_code == 200 and resp.json() == {"field": "chief_complaint", "suggestions": []}


async def test_suggestions_are_read_only_and_leave_historical_soap_untouched(client, make_clinic_with_owner, db_session) -> None:
    from sqlalchemy import select

    clinic, headers, deps = await _setup_clinic(client, make_clinic_with_owner)
    clinic_id = clinic.id
    await _two_patients_use(db_session, client, headers, clinic, deps, "chief_complaint", "  Mixed   CASE  ")
    before = sorted((await db_session.execute(select(SoapNote.chief_complaint, SoapNote.updated_at).where(SoapNote.clinic_id == clinic_id))).all())
    await _suggest(client, headers, "chief_complaint")
    db_session.expire_all()
    after = sorted((await db_session.execute(select(SoapNote.chief_complaint, SoapNote.updated_at).where(SoapNote.clinic_id == clinic_id))).all())
    assert before == after
    assert all(row[0] == "  Mixed   CASE  " for row in after)  # stored text is never normalized in place
