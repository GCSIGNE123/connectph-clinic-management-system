"""SOAP note (Phase 8).

Design decision - one-to-one with Consultation: a consultation has exactly
one SOAP note that is upserted in place on every autosave (`PUT
/consultations/{id}/soap`), not a new row per save. This keeps autosave
idempotent/cheap and matches the spec's "Save Progress ... autosave" flow;
a full point-in-time history of every draft edit is not required by spec,
only the final saved note plus the append-only `visit_timeline_events`
audit trail of *that a* save happened.
"""

import uuid

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SoapNote(UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "soap_notes"

    consultation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # --- Subjective ---
    chief_complaint: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_of_present_illness: Mapped[str | None] = mapped_column(Text, nullable=True)
    past_medical_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    family_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_of_systems: Mapped[str | None] = mapped_column(Text, nullable=True)
    subjective_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Objective ---
    blood_pressure: Mapped[str | None] = mapped_column(Text, nullable=True)
    pulse_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    respiratory_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)  # server-computed, see ConsultationService.save_soap
    oxygen_saturation: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Phase 21 (Vitals-before-Queue): Pain Score and Head Circumference are
    # both explicitly OPTIONAL per spec (Head Circumference additionally
    # gated by `Clinic.require_head_circumference` - see models/clinic.py).
    # Added here rather than a separate table since they're just two more
    # vitals fields on the same one-to-one SoapNote row as everything else
    # in this "Objective" section.
    pain_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    head_circumference_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    physical_examination: Mapped[str | None] = mapped_column(Text, nullable=True)
    clinical_findings: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Assessment ---
    clinical_impression: Mapped[str | None] = mapped_column(Text, nullable=True)
    differential_diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Plan ---
    treatment_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    referral_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    consultation: Mapped["Consultation"] = relationship(back_populates="soap_note")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SoapNote id={self.id} consultation_id={self.consultation_id}>"
