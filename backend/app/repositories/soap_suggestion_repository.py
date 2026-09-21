"""Read-only queries behind the SOAP/diagnosis learned suggestions (Task #2).

Aggregates a clinic's OWN existing SOAP / diagnosis text into candidate
suggestions. Nothing here writes, and every query is clinic-scoped. A value
is only a candidate when it was used in consultations of at least
`MIN_DISTINCT_PATIENTS` different patients - so text that belongs to one
patient's record never becomes a suggestion for another.
"""

from uuid import UUID

from sqlalchemy import Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation import Consultation
from app.models.diagnosis import Diagnosis
from app.models.soap_note import SoapNote

MIN_DISTINCT_PATIENTS = 2
MAX_SUGGESTION_LENGTH = 80
CANDIDATE_POOL = 60  # rows fetched before junk filtering; the service trims to the response limit

# Allowlist: request field -> (model, column). Never a raw column name from the client.
SOAP_SUGGESTION_FIELDS = {
    "chief_complaint": (SoapNote, SoapNote.chief_complaint),
    "physical_examination": (SoapNote, SoapNote.physical_examination),
    "clinical_findings": (SoapNote, SoapNote.clinical_findings),
    "clinical_impression": (SoapNote, SoapNote.clinical_impression),
    "differential_diagnosis": (SoapNote, SoapNote.differential_diagnosis),
    "treatment_plan": (SoapNote, SoapNote.treatment_plan),
    "patient_instructions": (SoapNote, SoapNote.patient_instructions),
    "followup_recommendation": (SoapNote, SoapNote.followup_recommendation),
    "icd10_code": (Diagnosis, Diagnosis.icd10_code),
    "icd10_description": (Diagnosis, Diagnosis.icd10_description),
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SoapSuggestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def candidates(self, clinic_id: UUID, field: str, q: str | None) -> list[str]:
        """Most-used distinct values for `field`, best first, as (whitespace-normalized) text.

        Rows are grouped case-insensitively; one display form is chosen
        deterministically (`min`). Multi-line values are skipped - the UI
        suggests one line/segment at a time.
        """
        model, column = SOAP_SUGGESTION_FIELDS[field]
        text_col = cast(column, Text)
        display = func.trim(func.regexp_replace(text_col, r"\s+", " ", "g"))
        key = func.lower(display)

        stmt = (
            select(func.min(display).label("display"))
            .select_from(model)
            .join(Consultation, Consultation.id == model.consultation_id)
            .where(
                model.clinic_id == clinic_id,
                Consultation.clinic_id == clinic_id,
                Consultation.is_deleted.is_(False),
                column.is_not(None),
                text_col.notlike("%" + "\n" + "%"),
                func.length(display) > 0,
                func.length(display) <= MAX_SUGGESTION_LENGTH,
            )
        )
        if model is Diagnosis:
            stmt = stmt.where(Diagnosis.is_deleted.is_(False))
        if q:
            stmt = stmt.where(key.like("%" + _escape_like(q.strip().lower()) + "%", escape="\\"))
        stmt = (
            stmt.group_by(key)
            .having(func.count(func.distinct(Consultation.patient_id)) >= MIN_DISTINCT_PATIENTS)
            .order_by(func.count(func.distinct(Consultation.patient_id)).desc(), key.asc())
            .limit(CANDIDATE_POOL)
        )
        return [row[0] for row in (await self.session.execute(stmt)).all() if row[0]]
