"""Pydantic schemas for the Pathologist master-data resource.

Deliberately minimal - mirrors only the subset of `DoctorBase`/`DoctorCreate`/
`DoctorRead` that's actually needed for a Laboratory Report signatory: name,
license number, e-signature, active state. No department/branch/photo/
consultation-fee/email - a Pathologist is not a Doctor and does not need
those fields.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PathologistBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    license_number: str | None = Field(default=None, max_length=50)
    is_active: bool = True


class PathologistCreate(PathologistBase):
    # `signature_url` is deliberately NOT settable here - it must only ever
    # be written by the dedicated, validated `/pathologists/{id}/signature`
    # upload endpoint, never as an arbitrary client-supplied string. Same
    # convention as `DoctorCreate.signature_url`.
    pass


class PathologistUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    license_number: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None


class PathologistRead(PathologistBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    signature_url: str | None = None
    created_at: datetime
    updated_at: datetime


class PathologistListResponse(BaseModel):
    items: list[PathologistRead]
    total: int
