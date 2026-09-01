"""Doctor model + doctor weekly availability schedule.

`DoctorSchedule` is architecture-only (a weekly availability window per
doctor/branch/day) - it deliberately has no notion of appointment slots or
bookings; that belongs to the future Appointments module.
"""

import enum
import uuid
from decimal import Decimal

from datetime import date as date_type

from typing import Any

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy import Boolean
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DoctorStatus(str, enum.Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    ON_LEAVE = "On Leave"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


# --- Per-doctor consultation workspace configuration ---
# Data-driven show/hide + required toggles for consultation sections, per
# doctor. Deliberately a single JSONB blob (like `LaboratoryTemplateParameter
# .options`) rather than a normalized table - the shape is small, fixed, and
# always read/written as a whole document, never queried by individual
# section. `CONSULTATION_SECTIONS` below is the ONE place new sections get
# added - nothing in the resolution/enforcement logic below ever names a
# specific doctor, so there are no hard-coded per-doctor exceptions anywhere
# in this feature.
CONSULTATION_SECTIONS: list[dict[str, str]] = [
    {"id": "vitals", "label": "Vitals"},
    {"id": "diagnosis", "label": "Diagnosis"},
    {"id": "prescription", "label": "Prescription"},
    {"id": "lab_requests", "label": "Lab Requests"},
    {"id": "certificate", "label": "Medical Certificate"},
    {"id": "attachments", "label": "Attachments"},
]
CONSULTATION_SECTION_IDS: frozenset[str] = frozenset(s["id"] for s in CONSULTATION_SECTIONS)

# --- Per-doctor SOAP field configuration ---
# Which individual SOAP note fields a doctor wants to see/use in their own
# consultation workflow. Deliberately a flat {field_id: bool} map inside the
# same `workspace_config` JSONB blob as `sections` above (see
# `resolve_workspace_config`) rather than a new column/table - this is the
# same "show/hide, data-driven, one config blob per doctor" shape as
# sections, just at field granularity instead of section granularity. There
# is no "required" concept here (unlike sections) - the SOAP checklist is a
# single visible/hidden toggle per field, per the feature spec.
# Field ids match the corresponding `SoapNote` column names 1:1 (see
# `models/soap_note.py`) so no translation layer is needed anywhere this
# config is consumed. `bmi` is the one exception - it has no `SoapNote`
# column of its own (it's server-computed from height/weight, see
# `ConsultationService._compute_bmi`); the toggle here only controls whether
# the BMI display row renders, never how BMI itself is calculated.
SOAP_FIELD_GROUPS: list[dict[str, Any]] = [
    {
        "id": "subjective",
        "label": "Subjective",
        "fields": [
            {"id": "chief_complaint", "label": "Chief complaint"},
            {"id": "history_of_present_illness", "label": "History of present illness"},
            {"id": "past_medical_history", "label": "Past medical history"},
            {"id": "family_history", "label": "Family history"},
            {"id": "social_history", "label": "Social history"},
            {"id": "review_of_systems", "label": "Review of systems"},
            {"id": "subjective_notes", "label": "Additional subjective notes"},
        ],
    },
    {
        "id": "objective",
        "label": "Objective / Vitals",
        "fields": [
            {"id": "blood_pressure", "label": "Blood pressure"},
            {"id": "pulse_rate", "label": "Pulse (bpm)"},
            {"id": "respiratory_rate", "label": "Respiratory rate"},
            {"id": "temperature", "label": "Temperature (°C)"},
            {"id": "height_cm", "label": "Height (cm)"},
            {"id": "weight_kg", "label": "Weight (kg)"},
            {"id": "bmi", "label": "BMI"},
            {"id": "oxygen_saturation", "label": "O₂ saturation (%)"},
            {"id": "physical_examination", "label": "Physical examination"},
            {"id": "clinical_findings", "label": "Clinical findings"},
        ],
    },
    {
        "id": "assessment",
        "label": "Assessment",
        "fields": [
            {"id": "clinical_impression", "label": "Clinical impression"},
            {"id": "differential_diagnosis", "label": "Differential diagnosis"},
            {"id": "assessment_notes", "label": "Assessment notes"},
        ],
    },
    {
        "id": "plan",
        "label": "Plan",
        "fields": [
            {"id": "treatment_plan", "label": "Treatment plan"},
            {"id": "patient_instructions", "label": "Patient instructions"},
            {"id": "followup_recommendation", "label": "Follow-up recommendation"},
            {"id": "referral_notes", "label": "Referral notes"},
        ],
    },
]
SOAP_FIELD_IDS: frozenset[str] = frozenset(f["id"] for group in SOAP_FIELD_GROUPS for f in group["fields"])


def default_workspace_config() -> dict[str, Any]:
    """Every section visible/none required, every SOAP field enabled - the
    exact behavior the consultation page already had before either feature
    existed. This is also what a doctor with no custom configuration (or a
    config saved before SOAP fields existed) resolves to."""
    return {
        "sections": {sid: {"visible": True, "required": False} for sid in CONSULTATION_SECTION_IDS},
        "soap_fields": {fid: True for fid in SOAP_FIELD_IDS},
    }


def _all_sections(*, visible: bool, required: bool) -> dict[str, dict[str, bool]]:
    return {sid: {"visible": visible, "required": required} for sid in CONSULTATION_SECTION_IDS}


# Presets are plain data (not per-doctor code paths) - applying one is just
# copying this dict as a doctor's `workspace_config`, the same write path as
# any hand-picked configuration. Presets only vary `sections` - all three
# leave `soap_fields` at "every field enabled" since the SOAP checklist is a
# separate, independently-configured concern (see `SOAP_FIELD_GROUPS`).
_DEFAULT_SOAP_FIELDS: dict[str, bool] = {fid: True for fid in SOAP_FIELD_IDS}
WORKSPACE_CONFIG_PRESETS: dict[str, dict[str, Any]] = {
    # Minimal encounter: core clinical sections only.
    "simple": {
        "sections": {
            **_all_sections(visible=False, required=False),
            "vitals": {"visible": True, "required": False},
            "diagnosis": {"visible": True, "required": False},
            "prescription": {"visible": True, "required": False},
        },
        "soap_fields": dict(_DEFAULT_SOAP_FIELDS),
    },
    # Matches the no-custom-config default exactly - every section visible,
    # nothing mandatory.
    "standard": default_workspace_config(),
    # Full encounter with the core clinical sections enforced as required.
    "comprehensive": {
        "sections": {
            **_all_sections(visible=True, required=False),
            "vitals": {"visible": True, "required": True},
            "diagnosis": {"visible": True, "required": True},
            "prescription": {"visible": True, "required": True},
        },
        "soap_fields": dict(_DEFAULT_SOAP_FIELDS),
    },
}


def resolve_workspace_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Merges a possibly partial/stale/absent stored config over the
    current defaults, section-by-section and SOAP-field-by-field:
    - No stored config at all -> full default (unchanged pre-feature
      behavior for every existing doctor).
    - A stored config missing a section/field that was added later still
      gets that section/field's default (enabled) rather than silently
      disappearing - this is what makes "existing doctors keep every SOAP
      field enabled after this feature ships" true without a migration
      needing to touch a single row.
    - An unknown/legacy section id or SOAP field id in stored data is
      ignored, never raises - only the API layer (`WorkspaceConfig`
      schema) rejects unknown ids up front; this function is the last line
      of defense for stale/hand-edited data and must never blow up.
    - A section marked required while NOT visible has `required` forced
      back to False here - the single place that invariant is enforced, so
      every caller (API responses, consultation rendering, completion
      validation) automatically agrees without re-checking it themselves."""
    resolved = default_workspace_config()
    sections = resolved["sections"]
    raw_sections = raw.get("sections") if isinstance(raw, dict) else None
    if isinstance(raw_sections, dict):
        for sid in CONSULTATION_SECTION_IDS:
            entry = raw_sections.get(sid)
            if isinstance(entry, dict):
                sections[sid]["visible"] = bool(entry.get("visible", True))
    for sid in CONSULTATION_SECTION_IDS:
        entry = raw_sections.get(sid) if isinstance(raw_sections, dict) else None
        required = bool(entry.get("required", False)) if isinstance(entry, dict) else False
        sections[sid]["required"] = required and sections[sid]["visible"]

    soap_fields = resolved["soap_fields"]
    raw_soap_fields = raw.get("soap_fields") if isinstance(raw, dict) else None
    if isinstance(raw_soap_fields, dict):
        for fid in SOAP_FIELD_IDS:
            if fid in raw_soap_fields:
                soap_fields[fid] = bool(raw_soap_fields[fid])
    return resolved


class Doctor(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "doctors"
    __table_args__ = (UniqueConstraint("clinic_id", "doctor_code", name="uq_doctor_clinic_code"),)

    doctor_code: Mapped[str] = mapped_column(String(30), nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)

    prc_license: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ptr_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    specialization: Mapped[str | None] = mapped_column(String(150), nullable=True)

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signature_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consultation_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)

    status: Mapped[DoctorStatus] = mapped_column(
        SAEnum(DoctorStatus, name="doctor_status", values_callable=_enum_values),
        nullable=False,
        default=DoctorStatus.ACTIVE,
        server_default=DoctorStatus.ACTIVE.value,
        index=True,
    )

    # Nullable = "no custom configuration" - `effective_workspace_config`
    # below resolves that to `default_workspace_config()` (every section
    # visible, none required), i.e. exactly the consultation page's
    # pre-existing behavior. Never read directly for rendering/enforcement -
    # always go through `resolve_workspace_config`/`effective_workspace_config`.
    workspace_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    department: Mapped["Department | None"] = relationship()
    branch: Mapped["Branch | None"] = relationship()
    schedules: Mapped[list["DoctorSchedule"]] = relationship(back_populates="doctor", cascade="all, delete-orphan")

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name, self.suffix]
        return " ".join(p for p in parts if p)

    @property
    def effective_workspace_config(self) -> dict[str, Any]:
        """The fully-resolved config (see `resolve_workspace_config`) - what
        every caller should actually read, never `workspace_config` (the
        raw, possibly-partial-or-null stored value) directly."""
        return resolve_workspace_config(self.workspace_config)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Doctor id={self.id} doctor_code={self.doctor_code!r}>"


class DoctorSchedule(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A weekly availability window for a doctor at a branch.

    Phase 4 shipped this as architecture-only (no slot/booking logic). Phase
    11 (Appointment Management) extends it additively - in place, rather
    than creating a parallel table - with the fields the Time Slot Engine
    needs: lunch break, slot duration, a soft daily cap, and support for a
    non-recurring date-bounded override (`is_recurring=False` +
    `effective_from`/`effective_to`) layered on top of the recurring weekly
    row. See docs/DATABASE.md for the rationale.
    """

    __tablename__ = "doctor_schedules"

    doctor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 0=Monday .. 6=Sunday
    start_time: Mapped[str] = mapped_column(Time, nullable=False)
    end_time: Mapped[str] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Phase 11 additions ---
    lunch_break_start: Mapped[str | None] = mapped_column(Time, nullable=True)
    lunch_break_end: Mapped[str | None] = mapped_column(Time, nullable=True)
    slot_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15, server_default="15")
    max_patients_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default="true")
    effective_from: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    doctor: Mapped["Doctor"] = relationship(back_populates="schedules")
    branch: Mapped["Branch | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DoctorSchedule id={self.id} doctor_id={self.doctor_id} day={self.day_of_week}>"
