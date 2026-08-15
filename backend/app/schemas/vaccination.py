"""Pydantic schemas for Vaccination Administration (Post-RC1)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.vaccination_administration import VaccinationStatus


class VaccinationAdministrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    visit_id: UUID
    patient_id: UUID
    # Feature 5: real display names, resolved from the already-eager-loaded
    # `patient`/`administered_by_user` relationships (see
    # `VaccinationRepository._options()`) - no new columns, no migration.
    patient_name: str | None = None
    doctor_id: UUID | None = None
    vaccine_name: str
    status: VaccinationStatus
    dose: str | None = None
    lot_number: str | None = None
    site: str | None = None
    route: str | None = None
    notes: str | None = None
    administered_at: datetime | None = None
    administered_by: UUID | None = None
    administered_by_name: str | None = None
    created_at: datetime


class VaccinationAdministerRequest(BaseModel):
    vaccine_name: str | None = Field(default=None, max_length=255, description="Override if the vaccine actually given differs from what was ordered.")
    dose: str | None = Field(default=None, max_length=100)
    lot_number: str | None = Field(default=None, max_length=100)
    site: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    administered_at: datetime | None = None
