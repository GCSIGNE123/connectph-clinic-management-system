"""Task #2 enhancement: a Doctor's personal SOAP phrases - "My Phrases" (favorites) and "Recently used".

Endpoints (siblings of the unchanged clinic-suggestions endpoint):
  GET    /consultations/soap-suggestions/personal?field=&q=
  POST   /consultations/soap-suggestions/favorites   {field, text}
  DELETE /consultations/soap-suggestions/favorites?field=&text=

Doctor role + a linked doctor_id only; scoped to (clinic, that Doctor, one field).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.consultation import Consultation, ConsultationStatus
from app.models.diagnosis import Diagnosis, DiagnosisType
from app.models.soap_note import SoapNote
from app.models.soap_phrase_favorite import SoapPhraseFavorite
from app.models.visit import Visit
from app.services.soap_personal_phrase_service import MAX_FAVORITES_PER_FIELD, extract_segments
from app.tests.test_billing import _login, _make_role_login, _setup_queue_deps

pytestmark = pytest.mark.asyncio

BASE = "/api/v1/consultations/soap-suggestions"
PERSONAL = BASE + "/personal"
FAVORITES = BASE + "/favorites"


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


async def _env(client: AsyncClient, make_clinic_with_owner, db):
    """A clinic with its queue deps and one logged-in Doctor (linked to deps['doctor_id'])."""
    clinic, owner, password = await make_clinic_with_owner()
    owner_headers = {"Authorization": f"Bearer {await _login(client, owner.email, password)}"}
    deps = await _setup_queue_deps(client, owner_headers)
    email, _user = await _make_role_login(db, clinic_id=clinic.id, role_name="Doctor", doctor_id=deps["doctor_id"])
    headers = {"Authorization": f"Bearer {await _login(client, email, 'TestPass123!')}"}
    return {"clinic": clinic, "clinic_id": clinic.id, "owner": owner_headers, "deps": deps, "doc": headers}


async def _second_doctor(client, db, env):
    """Another Doctor (own Doctor record + login) in the SAME clinic."""
    created = await client.post(
        "/api/v1/doctors", headers=env["owner"], json={"first_name": "Ana", "last_name": "Reyes", "consultation_fee": "300.00"}
    )
    assert created.status_code in (200, 201), created.text
    doctor_id = created.json()["id"]
    email, _u = await _make_role_login(db, clinic_id=env["clinic_id"], role_name="Doctor", doctor_id=doctor_id)
    return doctor_id, {"Authorization": f"Bearer {await _login(client, email, 'TestPass123!')}"}


async def _patient(client, headers, first="Pat", last="Test") -> str:
    n = _n()
    resp = await client.post(
        "/api/v1/patients", headers=headers,
        json={"first_name": first, "last_name": last, "birth_date": f"19{60 + n % 30}-01-15",
              "gender": "Male", "civil_status": "Single", "mobile_number": f"+63917{n:07d}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["patient"]["id"]


async def _consult(db, env, patient_id, *, doctor_id=None, soap=None, diagnoses=None,
                   status=ConsultationStatus.DRAFT, updated_at=None):
    n = _n()
    branch_id = uuid.UUID(env["deps"]["branch_id"])
    visit = Visit(
        clinic_id=env["clinic_id"], branch_id=branch_id, patient_id=uuid.UUID(patient_id),
        visit_number=f"VIS-P-{n:06d}", visit_date=datetime.now(UTC).date(),
    )
    db.add(visit)
    await db.flush()
    c = Consultation(
        clinic_id=env["clinic_id"], visit_id=visit.id, branch_id=branch_id,
        doctor_id=uuid.UUID(doctor_id or env["deps"]["doctor_id"]), patient_id=uuid.UUID(patient_id),
        started_at=datetime.now(UTC), status=status,
    )
    db.add(c)
    await db.flush()
    if soap is not None:
        extra = {"updated_at": updated_at} if updated_at else {}
        db.add(SoapNote(clinic_id=env["clinic_id"], consultation_id=c.id, **soap, **extra))
    for d in diagnoses or []:
        db.add(Diagnosis(clinic_id=env["clinic_id"], consultation_id=c.id, diagnosis_type=DiagnosisType.PRIMARY, **d))
    await db.commit()
    return c


async def _personal(client, headers, field, **params):
    resp = await client.get(PERSONAL, headers=headers, params={"field": field, **params})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["field"] == field and set(body) == {"field", "favorites", "recent"}
    return [x["text"] for x in body["favorites"]], [x["text"] for x in body["recent"]]


async def _fav(client, headers, field, text):
    return await client.post(FAVORITES, headers=headers, json={"field": field, "text": text})


# ---------------------------------------------------------------- favorites: CRUD / idempotency / cap


async def test_favorite_create_list_delete(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    created = await _fav(client, env["doc"], "chief_complaint", "  Fever   and cough  ")
    assert created.status_code == 201 and created.json() == {"field": "chief_complaint", "text": "Fever and cough"}
    assert await _personal(client, env["doc"], "chief_complaint") == (["Fever and cough"], [])

    removed = await client.delete(FAVORITES, headers=env["doc"], params={"field": "chief_complaint", "text": "FEVER AND COUGH"})
    assert removed.status_code == 204  # matching is case/whitespace-insensitive
    assert await _personal(client, env["doc"], "chief_complaint") == ([], [])
    again = await client.delete(FAVORITES, headers=env["doc"], params={"field": "chief_complaint", "text": "Fever and cough"})
    assert again.status_code == 404


async def test_duplicate_favorite_is_idempotent(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    first = await _fav(client, env["doc"], "chief_complaint", "Headache")
    dup1 = await _fav(client, env["doc"], "chief_complaint", "Headache")
    dup2 = await _fav(client, env["doc"], "chief_complaint", "  headache ")  # case/whitespace variant
    assert first.status_code == 201 and dup1.status_code == 200 and dup2.status_code == 200
    assert dup2.json()["text"] == "Headache"  # the originally saved display form
    rows = (await db_session.execute(select(SoapPhraseFavorite).where(SoapPhraseFavorite.clinic_id == env["clinic_id"]))).scalars().all()
    assert len(rows) == 1


async def test_favorites_are_capped_per_field(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    for i in range(MAX_FAVORITES_PER_FIELD):
        assert (await _fav(client, env["doc"], "treatment_plan", f"Phrase number {i:02d}")).status_code == 201
    over = await _fav(client, env["doc"], "treatment_plan", "One too many")
    assert over.status_code == 409
    assert (await _fav(client, env["doc"], "treatment_plan", "phrase number 00")).status_code == 200  # duplicate still idempotent at the cap
    assert (await _fav(client, env["doc"], "chief_complaint", "Fits in another field")).status_code == 201  # cap is per field
    assert (await client.delete(FAVORITES, headers=env["doc"], params={"field": "treatment_plan", "text": "Phrase number 01"})).status_code == 204
    assert (await _fav(client, env["doc"], "treatment_plan", "Now there is room")).status_code == 201


async def test_favorites_are_listed_newest_first(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    for text in ("Alpha", "Bravo", "Charlie"):
        await _fav(client, env["doc"], "chief_complaint", text)
    favorites, _ = await _personal(client, env["doc"], "chief_complaint")
    assert favorites == ["Charlie", "Bravo", "Alpha"]
    assert await _personal(client, env["doc"], "chief_complaint") == (favorites, [])  # deterministic


# ---------------------------------------------------------------- validation / privacy


@pytest.mark.parametrize(
    "text",
    [
        "", "   ", "!!!", ("cough " * 14)[:81],  # 81 characters: one over the limit
        "line one\nline two",
        "email me at a.b@example.com", "see https://example.com/x", "call +63 917 123 4567",
        "patient PAT-000123 again", "id 3fa85f64-5717-4562-b3fc-2c963f66afa6", "test entry", "regression note",
    ],
)
async def test_favorite_validation_rejects_unsafe_or_unusable_text(client, make_clinic_with_owner, db_session, text) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    resp = await _fav(client, env["doc"], "chief_complaint", text)
    assert resp.status_code == 422, (text, resp.text)
    assert await _personal(client, env["doc"], "chief_complaint") == ([], [])


async def test_favorite_accepts_short_clinical_phrase_and_icd_code(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    at_limit = ("cough " * 14)[:80]
    assert len(at_limit) == 80 and at_limit == at_limit.strip()
    assert (await _fav(client, env["doc"], "chief_complaint", at_limit)).status_code == 201  # exactly the limit
    assert (await _fav(client, env["doc"], "icd10_code", "J06.9")).status_code == 201  # code-like text is fine for ICD-10
    assert (await _fav(client, env["doc"], "icd10_description", "Acute upper respiratory infection, unspecified")).status_code == 201


async def test_unsupported_field_and_extra_body_keys_are_422(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    assert (await _fav(client, env["doc"], "assessment_notes", "Anything")).status_code == 422
    assert (await client.get(PERSONAL, headers=env["doc"], params={"field": "referral_notes"})).status_code == 422
    assert (await client.delete(FAVORITES, headers=env["doc"], params={"field": "nope", "text": "x"})).status_code == 422
    resp = await client.post(FAVORITES, headers=env["doc"], json={"field": "chief_complaint", "text": "Ok", "doctor_id": str(uuid.uuid4())})
    assert resp.status_code == 422  # a client can never choose the owner


# ---------------------------------------------------------------- scoping: doctor / clinic / field


async def test_favorites_are_scoped_to_the_doctor(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    _doc_b_id, headers_b = await _second_doctor(client, db_session, env)
    await _fav(client, env["doc"], "chief_complaint", "Doctor A phrase")
    assert await _personal(client, headers_b, "chief_complaint") == ([], [])  # B cannot see A's
    assert (await client.delete(FAVORITES, headers=headers_b, params={"field": "chief_complaint", "text": "Doctor A phrase"})).status_code == 404
    assert await _personal(client, env["doc"], "chief_complaint") == (["Doctor A phrase"], [])  # and B could not remove it
    # Both may hold the same phrase independently.
    assert (await _fav(client, headers_b, "chief_complaint", "Doctor A phrase")).status_code == 201
    assert (await client.delete(FAVORITES, headers=headers_b, params={"field": "chief_complaint", "text": "Doctor A phrase"})).status_code == 204
    assert await _personal(client, env["doc"], "chief_complaint") == (["Doctor A phrase"], [])


async def test_favorites_are_isolated_between_clinics(client, make_clinic_with_owner, db_session) -> None:
    env_a = await _env(client, make_clinic_with_owner, db_session)
    env_b = await _env(client, make_clinic_with_owner, db_session)
    await _fav(client, env_a["doc"], "chief_complaint", "Clinic A only")
    assert await _personal(client, env_b["doc"], "chief_complaint") == ([], [])
    assert (await client.delete(FAVORITES, headers=env_b["doc"], params={"field": "chief_complaint", "text": "Clinic A only"})).status_code == 404


async def test_favorites_and_recent_are_isolated_between_fields(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    await _fav(client, env["doc"], "chief_complaint", "Only for complaints")
    await _consult(db_session, env, await _patient(client, env["owner"]), soap={"treatment_plan": "Only for plans"})
    assert await _personal(client, env["doc"], "chief_complaint") == (["Only for complaints"], [])
    assert await _personal(client, env["doc"], "treatment_plan") == ([], ["Only for plans"])
    assert await _personal(client, env["doc"], "patient_instructions") == ([], [])
    assert await _personal(client, env["doc"], "physical_examination") == ([], [])


# ---------------------------------------------------------------- recently used


async def test_recent_comes_only_from_the_authenticated_doctors_own_consultations(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    doc_b_id, headers_b = await _second_doctor(client, db_session, env)
    await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": "Mine"})
    await _consult(db_session, env, await _patient(client, env["owner"]), doctor_id=doc_b_id, soap={"chief_complaint": "Theirs"})
    assert (await _personal(client, env["doc"], "chief_complaint"))[1] == ["Mine"]
    assert (await _personal(client, headers_b, "chief_complaint"))[1] == ["Theirs"]


async def test_recent_is_clinic_isolated(client, make_clinic_with_owner, db_session) -> None:
    env_a = await _env(client, make_clinic_with_owner, db_session)
    env_b = await _env(client, make_clinic_with_owner, db_session)
    await _consult(db_session, env_a, await _patient(client, env_a["owner"]), soap={"chief_complaint": "Clinic A note"})
    assert (await _personal(client, env_a["doc"], "chief_complaint"))[1] == ["Clinic A note"]
    assert (await _personal(client, env_b["doc"], "chief_complaint"))[1] == []


async def test_recent_needs_no_patient_threshold_and_ignores_consultation_status(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    for status, text in ((ConsultationStatus.DRAFT, "From draft"), (ConsultationStatus.IN_PROGRESS, "From in progress"),
                         (ConsultationStatus.COMPLETED, "From completed"), (ConsultationStatus.SIGNED, "From signed")):
        await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": text}, status=status)
    recent = (await _personal(client, env["doc"], "chief_complaint"))[1]
    assert sorted(recent) == ["From completed", "From draft", "From in progress", "From signed"]
    # ...while the clinic-wide list (2-patient rule) still shows none of these single-patient values.
    clinic = await client.get(BASE, headers=env["doc"], params={"field": "chief_complaint"})
    assert clinic.status_code == 200 and clinic.json() == {"field": "chief_complaint", "suggestions": []}


async def test_recent_is_newest_first_deduplicated_and_deterministic(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    now = datetime.now(UTC)
    for text, age in (("Oldest", 5), ("Middle", 3), ("headache", 2), ("Headache", 1), ("Newest", 0)):
        await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": text}, updated_at=now - timedelta(days=age))
    recent = (await _personal(client, env["doc"], "chief_complaint"))[1]
    assert recent == ["Newest", "Headache", "Middle", "Oldest"]  # case-insensitive duplicate kept once, at its newest use
    assert (await _personal(client, env["doc"], "chief_complaint"))[1] == recent


async def test_recent_is_bounded(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    now = datetime.now(UTC)
    for i in range(14):
        await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": f"Complaint {i:02d}"}, updated_at=now - timedelta(minutes=i))
    assert len((await _personal(client, env["doc"], "chief_complaint"))[1]) == 10  # default bound
    assert len((await _personal(client, env["doc"], "chief_complaint", limit=3))[1]) == 3
    assert (await _personal(client, env["doc"], "chief_complaint", limit=3))[1] == ["Complaint 00", "Complaint 01", "Complaint 02"]
    assert (await client.get(PERSONAL, headers=env["doc"], params={"field": "chief_complaint", "limit": 21})).status_code == 422


async def test_recent_splits_multiline_text_into_eligible_lines_only(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    long_line = "y" * 90
    plan = f"Rest and hydration\n\n  Take   paracetamol 500mg  \n{long_line}\n-\nreach me at 09171234567\nRest and hydration"
    await _consult(db_session, env, await _patient(client, env["owner"]), soap={"treatment_plan": plan})
    recent = (await _personal(client, env["doc"], "treatment_plan"))[1]
    assert recent == ["Rest and hydration", "Take paracetamol 500mg"]  # blank/over-long/symbol-only/phone lines dropped; duplicate once
    assert plan not in recent  # the whole block is never a phrase


async def test_recent_applies_the_privacy_and_junk_filters(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    bad = ["ping a.b@example.com", "https://example.com/x", "call +63 917 123 4567", "PAT-000123 follow up",
           "id 3fa85f64-5717-4562-b3fc-2c963f66afa6", "test note", "regression check", "abcdefghij123 code"]
    for text in bad + ["Sore throat"]:
        await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": text})
    assert (await _personal(client, env["doc"], "chief_complaint"))[1] == ["Sore throat"]


async def test_recent_drops_phrases_that_contain_the_patients_name(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    marisol = await _patient(client, env["owner"], first="Marisol", last="Villanueva")
    await _consult(db_session, env, marisol, soap={"treatment_plan": "Marisol to return next week\nDrink plenty of water\nMs Villanueva is allergic"})
    other = await _patient(client, env["owner"], first="Jun", last="Cruz")
    await _consult(db_session, env, other, soap={"treatment_plan": "Marisol is a common name here"})  # another patient's note may mention it
    recent = (await _personal(client, env["doc"], "treatment_plan"))[1]
    assert "Drink plenty of water" in recent
    assert all("Villanueva" not in r for r in recent)
    assert "Marisol to return next week" not in recent  # the patient's own first name
    assert "Marisol is a common name here" in recent  # not this patient's name - still an allowed phrase


async def test_recent_and_favorites_do_not_duplicate_and_filter_by_q(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    now = datetime.now(UTC)
    for i, text in enumerate(("Cough", "Fever", "Cough and colds")):
        await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": text}, updated_at=now - timedelta(minutes=i))
    await _fav(client, env["doc"], "chief_complaint", "cough")  # favorited: leaves Recent, stays in My Phrases only
    favorites, recent = await _personal(client, env["doc"], "chief_complaint")
    assert favorites == ["cough"] and recent == ["Fever", "Cough and colds"]
    assert await _personal(client, env["doc"], "chief_complaint", q="COL") == ([], ["Cough and colds"])
    assert await _personal(client, env["doc"], "chief_complaint", q="cou") == (["cough"], ["Cough and colds"])


async def test_recent_for_diagnosis_fields(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    doc_b_id, headers_b = await _second_doctor(client, db_session, env)
    await _consult(db_session, env, await _patient(client, env["owner"]), diagnoses=[{"icd10_code": "J06.9", "icd10_description": "Acute URI, unspecified"}])
    await _consult(db_session, env, await _patient(client, env["owner"]), doctor_id=doc_b_id, diagnoses=[{"icd10_code": "I10", "icd10_description": "Hypertension"}])
    assert (await _personal(client, env["doc"], "icd10_code"))[1] == ["J06.9"]
    assert (await _personal(client, env["doc"], "icd10_description"))[1] == ["Acute URI, unspecified"]
    assert (await _personal(client, headers_b, "icd10_code"))[1] == ["I10"]


async def test_personal_endpoints_never_modify_historical_soap(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    clinic_id = env["clinic_id"]
    await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": "  Mixed   CASE  "})
    before = sorted((await db_session.execute(select(SoapNote.chief_complaint, SoapNote.updated_at).where(SoapNote.clinic_id == clinic_id))).all())
    await _personal(client, env["doc"], "chief_complaint")
    await _fav(client, env["doc"], "chief_complaint", "Mixed case")
    db_session.expire_all()
    after = sorted((await db_session.execute(select(SoapNote.chief_complaint, SoapNote.updated_at).where(SoapNote.clinic_id == clinic_id))).all())
    assert before == after and after[0][0] == "  Mixed   CASE  "


async def test_responses_carry_phrase_text_only(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    c = await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": "Dizziness"})
    resp = await client.get(PERSONAL, headers=env["doc"], params={"field": "chief_complaint"})
    assert resp.json() == {"field": "chief_complaint", "favorites": [], "recent": [{"text": "Dizziness"}]}
    for needle in (str(c.id), str(c.patient_id), str(c.visit_id), str(env["deps"]["doctor_id"])):
        assert needle not in resp.text
    made = await _fav(client, env["doc"], "chief_complaint", "Dizziness")
    assert set(made.json()) == {"field", "text"}


# ---------------------------------------------------------------- roles


async def test_only_a_doctor_with_a_linked_record_can_use_the_personal_endpoints(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    denied = ["Receptionist", "Nurse", "Owner", "Administrator", "Cashier", "Laboratory"]
    for role in denied:
        email, _u = await _make_role_login(db_session, clinic_id=env["clinic_id"], role_name=role, doctor_id=env["deps"]["doctor_id"] if role in ("Owner", "Administrator") else None)
        headers = {"Authorization": f"Bearer {await _login(client, email, 'TestPass123!')}"}
        assert (await client.get(PERSONAL, headers=headers, params={"field": "chief_complaint"})).status_code == 403, role
        assert (await _fav(client, headers, "chief_complaint", "Nope")).status_code == 403, role
        assert (await client.delete(FAVORITES, headers=headers, params={"field": "chief_complaint", "text": "Nope"})).status_code == 403, role
    # A Doctor login with NO linked doctor record is refused too.
    email, _u = await _make_role_login(db_session, clinic_id=env["clinic_id"], role_name="Doctor")
    unlinked = {"Authorization": f"Bearer {await _login(client, email, 'TestPass123!')}"}
    assert (await client.get(PERSONAL, headers=unlinked, params={"field": "chief_complaint"})).status_code == 403
    assert (await _fav(client, unlinked, "chief_complaint", "Nope")).status_code == 403
    for method, kwargs in (("get", {"params": {"field": "chief_complaint"}}), ("post", {"json": {"field": "chief_complaint", "text": "x"}}),
                           ("delete", {"params": {"field": "chief_complaint", "text": "x"}})):
        url = PERSONAL if method == "get" else FAVORITES
        assert (await getattr(client, method)(url, **kwargs)).status_code in (401, 403)
    assert (await db_session.execute(select(SoapPhraseFavorite).where(SoapPhraseFavorite.clinic_id == env["clinic_id"]))).first() is None  # nothing was written by refused calls


# ---------------------------------------------------------------- the existing clinic endpoint is unchanged


async def test_clinic_suggestions_endpoint_is_unchanged(client, make_clinic_with_owner, db_session) -> None:
    env = await _env(client, make_clinic_with_owner, db_session)
    for _ in range(2):
        await _consult(db_session, env, await _patient(client, env["owner"]), soap={"chief_complaint": "Headache"})
    await _fav(client, env["doc"], "chief_complaint", "My private phrase")
    resp = await client.get(BASE, headers=env["doc"], params={"field": "chief_complaint"})
    assert resp.status_code == 200
    assert resp.json() == {"field": "chief_complaint", "suggestions": [{"text": "Headache"}]}  # same shape; personal phrases never leak in
    # Receptionist/Nurse (Task #6) still get the clinic list for chief_complaint only.
    for role in ("Receptionist", "Nurse"):
        email, _u = await _make_role_login(db_session, clinic_id=env["clinic_id"], role_name=role)
        headers = {"Authorization": f"Bearer {await _login(client, email, 'TestPass123!')}"}
        assert (await client.get(BASE, headers=headers, params={"field": "chief_complaint"})).status_code == 200
        assert (await client.get(BASE, headers=headers, params={"field": "treatment_plan"})).status_code == 403


async def test_extract_segments_unit() -> None:
    assert extract_segments("a\r\n b  c \n\n-\n" + "z" * 81 + "\nlast") == ["a", "b c", "last"]
    assert extract_segments("") == []
