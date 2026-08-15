"""Repository for Consultation / SOAP / Diagnosis / Attachments (Phase 8)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.consultation import Consultation
from app.models.consultation_attachment import ConsultationAttachment
from app.models.diagnosis import Diagnosis
from app.models.soap_note import SoapNote


class ConsultationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Consultation ("latest wins" - see models/consultation.py) ---

    async def get_latest_for_visit(self, visit_id: UUID, clinic_id: UUID) -> Consultation | None:
        stmt = (
            select(Consultation)
            .where(Consultation.visit_id == visit_id, Consultation.clinic_id == clinic_id, Consultation.is_deleted.is_(False))
            .options(selectinload(Consultation.soap_note), selectinload(Consultation.doctor), selectinload(Consultation.patient), selectinload(Consultation.visit))
            .order_by(Consultation.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_latest_for_visits(self, visit_ids: list[UUID], clinic_id: UUID) -> dict[UUID, Consultation]:
        """Batched form of `get_latest_for_visit` - one query for a whole
        page of queue tickets (e.g. the Reception Queue table's "is vitals
        taken" indicator) instead of one query per row. Returns only the
        latest (most recently created) consultation per visit_id, matching
        `get_latest_for_visit`'s own "latest wins" semantics."""
        if not visit_ids:
            return {}
        stmt = (
            select(Consultation)
            .where(Consultation.visit_id.in_(visit_ids), Consultation.clinic_id == clinic_id, Consultation.is_deleted.is_(False))
            .options(selectinload(Consultation.soap_note))
            .order_by(Consultation.visit_id, Consultation.created_at.desc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        latest_by_visit: dict[UUID, Consultation] = {}
        for row in rows:
            if row.visit_id not in latest_by_visit:
                latest_by_visit[row.visit_id] = row
        return latest_by_visit

    async def get_by_id(self, consultation_id: UUID, clinic_id: UUID) -> Consultation | None:
        stmt = (
            select(Consultation)
            .where(Consultation.id == consultation_id, Consultation.clinic_id == clinic_id, Consultation.is_deleted.is_(False))
            .options(selectinload(Consultation.soap_note), selectinload(Consultation.doctor), selectinload(Consultation.patient), selectinload(Consultation.visit))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_consultation(
        self, *, clinic_id: UUID, visit_id: UUID, branch_id: UUID, doctor_id: UUID, patient_id: UUID,
        started_at: datetime, actor_id: UUID | None,
    ) -> Consultation:
        consultation = Consultation(
            clinic_id=clinic_id, visit_id=visit_id, branch_id=branch_id, doctor_id=doctor_id,
            patient_id=patient_id, started_at=started_at, created_by=actor_id, updated_by=actor_id,
        )
        self.session.add(consultation)
        await self.session.flush()
        await self.session.refresh(consultation, attribute_names=["doctor", "patient", "visit"])
        return consultation

    async def update_consultation(self, consultation: Consultation, **fields) -> Consultation:
        for key, value in fields.items():
            setattr(consultation, key, value)
        await self.session.flush()
        return consultation

    async def list_previous_for_patient(self, patient_id: UUID, clinic_id: UUID, *, exclude_id: UUID | None = None) -> list[Consultation]:
        filters = [Consultation.patient_id == patient_id, Consultation.clinic_id == clinic_id, Consultation.is_deleted.is_(False)]
        stmt = select(Consultation).where(*filters).options(selectinload(Consultation.soap_note)).order_by(Consultation.started_at.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        if exclude_id is not None:
            rows = [r for r in rows if r.id != exclude_id]
        return list(rows)

    # --- SOAP note (one-to-one, upsert) ---

    async def get_soap(self, consultation_id: UUID, clinic_id: UUID) -> SoapNote | None:
        stmt = select(SoapNote).where(SoapNote.consultation_id == consultation_id, SoapNote.clinic_id == clinic_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_soap(self, *, consultation_id: UUID, clinic_id: UUID, fields: dict) -> SoapNote:
        existing = await self.get_soap(consultation_id, clinic_id)
        if existing is None:
            note = SoapNote(consultation_id=consultation_id, clinic_id=clinic_id, **fields)
            self.session.add(note)
            await self.session.flush()
            return note
        for key, value in fields.items():
            setattr(existing, key, value)
        await self.session.flush()
        return existing

    # --- Diagnoses ---

    async def add_diagnosis(self, *, consultation_id: UUID, clinic_id: UUID, actor_id: UUID | None, **fields) -> Diagnosis:
        diagnosis = Diagnosis(consultation_id=consultation_id, clinic_id=clinic_id, created_by=actor_id, **fields)
        self.session.add(diagnosis)
        await self.session.flush()
        return diagnosis

    async def get_diagnosis(self, diagnosis_id: UUID, consultation_id: UUID, clinic_id: UUID) -> Diagnosis | None:
        stmt = select(Diagnosis).where(
            Diagnosis.id == diagnosis_id, Diagnosis.consultation_id == consultation_id,
            Diagnosis.clinic_id == clinic_id, Diagnosis.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_diagnoses(self, consultation_id: UUID, clinic_id: UUID) -> list[Diagnosis]:
        stmt = select(Diagnosis).where(
            Diagnosis.consultation_id == consultation_id, Diagnosis.clinic_id == clinic_id, Diagnosis.is_deleted.is_(False)
        ).order_by(Diagnosis.created_at.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def update_diagnosis(self, diagnosis: Diagnosis, **fields) -> Diagnosis:
        for key, value in fields.items():
            setattr(diagnosis, key, value)
        await self.session.flush()
        return diagnosis

    # --- Attachments ---

    async def add_attachment(self, *, consultation_id: UUID, clinic_id: UUID, uploaded_by: UUID | None, **fields) -> ConsultationAttachment:
        attachment = ConsultationAttachment(consultation_id=consultation_id, clinic_id=clinic_id, uploaded_by=uploaded_by, **fields)
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def list_attachments(self, consultation_id: UUID, clinic_id: UUID) -> list[ConsultationAttachment]:
        stmt = select(ConsultationAttachment).where(
            ConsultationAttachment.consultation_id == consultation_id,
            ConsultationAttachment.clinic_id == clinic_id,
            ConsultationAttachment.is_deleted.is_(False),
        ).order_by(ConsultationAttachment.created_at.desc())
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def get_attachment(self, attachment_id: UUID, consultation_id: UUID, clinic_id: UUID) -> ConsultationAttachment | None:
        stmt = select(ConsultationAttachment).where(
            ConsultationAttachment.id == attachment_id,
            ConsultationAttachment.consultation_id == consultation_id,
            ConsultationAttachment.clinic_id == clinic_id,
            ConsultationAttachment.is_deleted.is_(False),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()
