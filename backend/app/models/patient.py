"""Patient model - the master patient record shared by every clinical module."""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import (
    LegacyMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class Gender(str, enum.Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"


class CivilStatus(str, enum.Enum):
    SINGLE = "Single"
    MARRIED = "Married"
    WIDOWED = "Widowed"
    SEPARATED = "Separated"
    DIVORCED = "Divorced"


class BloodType(str, enum.Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    AB_POS = "AB+"
    AB_NEG = "AB-"
    O_POS = "O+"
    O_NEG = "O-"
    UNKNOWN = "Unknown"


class PatientStatus(str, enum.Enum):
    """Coarse-grained business status, distinct from soft-delete (which is
    reserved for records erroneously created / permanently removed)."""

    ACTIVE = "Active"
    ARCHIVED = "Archived"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Patient(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    """A patient record belonging to a clinic tenant (and optionally a branch).

    This is the master patient database referenced by every future clinical
    module (queue, appointments, billing, laboratory, pharmacy, medical
    records, reports). Only patient demographic/contact/medical-summary data
    lives here - visit history, appointments, billing, etc. are out of scope
    for this phase and will reference `Patient.id` from their own tables.
    """

    __tablename__ = "patients"

    # `legacy_id`/`legacy_meta` (LegacyMixin) already cover provenance from a
    # migrated system in a generic way. `legacy_patient_id` is kept as an
    # explicit, patient-specific external identifier (e.g. the old desktop
    # app's own patient number) since it is searched on directly and may
    # differ in shape from the generic `legacy_id` used elsewhere.
    legacy_patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("branches.id", ondelete="SET NULL"), nullable=True, index=True
    )

    patient_number: Mapped[str] = mapped_column(String(30), nullable=False)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    suffix: Mapped[str | None] = mapped_column(String(20), nullable=True)

    birth_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    gender: Mapped[Gender] = mapped_column(
        SAEnum(Gender, name="patient_gender", values_callable=_enum_values), nullable=False
    )
    civil_status: Mapped[CivilStatus] = mapped_column(
        SAEnum(CivilStatus, name="patient_civil_status", values_callable=_enum_values), nullable=False
    )
    nationality: Mapped[str] = mapped_column(String(100), nullable=False, server_default="Filipino")

    address_line: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barangay: Mapped[str | None] = mapped_column(String(150), nullable=True)
    city: Mapped[str | None] = mapped_column(String(150), nullable=True)
    province: Mapped[str | None] = mapped_column(String(150), nullable=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    mobile_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    telephone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    occupation: Mapped[str | None] = mapped_column(String(150), nullable=True)
    employer: Mapped[str | None] = mapped_column(String(150), nullable=True)

    blood_type: Mapped[BloodType | None] = mapped_column(
        SAEnum(BloodType, name="patient_blood_type", values_callable=_enum_values), nullable=True
    )
    allergies: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Additive nullable columns (Phase 8 - Phase 7 TODO). Consultation Patient
    # Summary header displays these; no UI existed to capture them before.
    emergency_contact_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    emergency_contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    medical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    qr_code: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Phase 2.7 (YAKAP Patient Classification): the patient's STANDING
    # PhilHealth YAKAP beneficiary status - a patient-profile-level fact,
    # separate from `Queue.visit_classification` (the per-ENCOUNTER
    # classification set at ticket-creation time, pre-filled from this flag
    # but independently editable - not every visit by a YAKAP beneficiary is
    # necessarily processed as a YAKAP encounter). Defaults False so every
    # existing patient record is unaffected.
    is_yakap_beneficiary: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    status: Mapped[PatientStatus] = mapped_column(
        SAEnum(PatientStatus, name="patient_status", values_callable=_enum_values),
        nullable=False,
        default=PatientStatus.ACTIVE,
        server_default=PatientStatus.ACTIVE.value,
        index=True,
    )

    date_registered: Mapped[date] = mapped_column(Date, nullable=False)
    last_visit: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    clinic: Mapped["Clinic"] = relationship()
    branch: Mapped["Branch | None"] = relationship()

    __table_args__ = (
        UniqueConstraint("clinic_id", "patient_number", name="uq_patient_clinic_patient_number"),
        Index("ix_patients_clinic_lastname_firstname", "clinic_id", "last_name", "first_name"),
        Index("ix_patients_clinic_mobile", "clinic_id", "mobile_number"),
        Index("ix_patients_clinic_birthdate", "clinic_id", "birth_date"),
    )

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name, self.suffix]
        return " ".join(p for p in parts if p)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Patient id={self.id} patient_number={self.patient_number!r}>"
