"""Queries behind a Doctor's personal SOAP phrases (Task #2 enhancement).

Two things, both scoped to (clinic, Doctor):

* `recent_rows` - the Doctor's OWN previously saved values for one field, newest
  first, read straight from existing `soap_notes` / `diagnoses` rows through
  `Consultation.doctor_id`. Nothing is written or migrated; there is no
  patient-count threshold (that safeguard belongs to the clinic-wide list). The
  patient's name parts are returned alongside ONLY so the service can drop a
  value that contains them - they are never sent to the client.
* favorites CRUD on `soap_phrase_favorites`.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Text, cast, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consultation import Consultation
from app.models.diagnosis import Diagnosis
from app.models.patient import Patient
from app.models.soap_phrase_favorite import SoapPhraseFavorite
from app.repositories.soap_suggestion_repository import SOAP_SUGGESTION_FIELDS

# How many of the Doctor's most recent saved values (notes / diagnoses) are scanned per request.
RECENT_ROW_POOL = 80


class RecentRow:
    """One saved value plus the name parts of the patient it belongs to (filter input only)."""

    __slots__ = ("text", "used_at", "name_parts")

    def __init__(self, text: str, used_at: datetime, name_parts: tuple[str, ...]) -> None:
        self.text = text
        self.used_at = used_at
        self.name_parts = name_parts


class SoapPersonalPhraseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def recent_rows(self, clinic_id: UUID, doctor_id: UUID, field: str) -> list[RecentRow]:
        model, column = SOAP_SUGGESTION_FIELDS[field]
        stmt = (
            select(cast(column, Text), model.updated_at, Patient.first_name, Patient.middle_name, Patient.last_name)
            .select_from(model)
            .join(Consultation, Consultation.id == model.consultation_id)
            .join(Patient, Patient.id == Consultation.patient_id)
            .where(
                model.clinic_id == clinic_id,
                Consultation.clinic_id == clinic_id,
                Consultation.doctor_id == doctor_id,
                Consultation.is_deleted.is_(False),
                column.is_not(None),
                func.length(func.trim(cast(column, Text))) > 0,
            )
            .order_by(model.updated_at.desc(), model.id.asc())
            .limit(RECENT_ROW_POOL)
        )
        if model is Diagnosis:
            stmt = stmt.where(Diagnosis.is_deleted.is_(False))
        rows = (await self.session.execute(stmt)).all()
        return [RecentRow(r[0], r[1], tuple(p for p in (r[2], r[3], r[4]) if p)) for r in rows]

    # --- favorites -----------------------------------------------------------------------

    async def list_favorites(self, clinic_id: UUID, doctor_id: UUID, field: str) -> list[SoapPhraseFavorite]:
        stmt = (
            select(SoapPhraseFavorite)
            .where(
                SoapPhraseFavorite.clinic_id == clinic_id,
                SoapPhraseFavorite.doctor_id == doctor_id,
                SoapPhraseFavorite.field == field,
            )
            .order_by(SoapPhraseFavorite.created_at.desc(), SoapPhraseFavorite.phrase_key.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def count_favorites(self, clinic_id: UUID, doctor_id: UUID, field: str) -> int:
        stmt = select(func.count()).select_from(SoapPhraseFavorite).where(
            SoapPhraseFavorite.clinic_id == clinic_id,
            SoapPhraseFavorite.doctor_id == doctor_id,
            SoapPhraseFavorite.field == field,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def get_favorite(self, clinic_id: UUID, doctor_id: UUID, field: str, phrase_key: str) -> SoapPhraseFavorite | None:
        stmt = select(SoapPhraseFavorite).where(
            SoapPhraseFavorite.clinic_id == clinic_id,
            SoapPhraseFavorite.doctor_id == doctor_id,
            SoapPhraseFavorite.field == field,
            SoapPhraseFavorite.phrase_key == phrase_key,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    def add_favorite(self, *, clinic_id: UUID, doctor_id: UUID, field: str, phrase: str, phrase_key: str) -> SoapPhraseFavorite:
        row = SoapPhraseFavorite(clinic_id=clinic_id, doctor_id=doctor_id, field=field, phrase=phrase, phrase_key=phrase_key)
        self.session.add(row)
        return row

    async def delete_favorite(self, clinic_id: UUID, doctor_id: UUID, field: str, phrase_key: str) -> int:
        stmt = delete(SoapPhraseFavorite).where(
            SoapPhraseFavorite.clinic_id == clinic_id,
            SoapPhraseFavorite.doctor_id == doctor_id,
            SoapPhraseFavorite.field == field,
            SoapPhraseFavorite.phrase_key == phrase_key,
        )
        result = await self.session.execute(stmt)
        return result.rowcount or 0
