"""Pydantic schemas for Clinical Orders & Prescriptions (Phase 9)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.order import OrderCategory, OrderPriority, OrderStatus
from app.models.prescription import PrescriptionStatus


# --- Orders ---

class OrderItemCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    item_category: str | None = Field(default=None, max_length=100)
    exam_type: str | None = Field(default=None, max_length=255)
    body_part: str | None = Field(default=None, max_length=255)
    clinical_indication: str | None = None


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_name: str
    item_category: str | None = None
    exam_type: str | None = None
    body_part: str | None = None
    clinical_indication: str | None = None


class OrderCreate(BaseModel):
    order_category: OrderCategory
    priority: OrderPriority = OrderPriority.ROUTINE
    scheduled_date: date | None = None
    clinical_notes: str | None = None
    items: list[OrderItemCreate] = Field(default_factory=list, min_length=1)


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    visit_id: UUID
    patient_id: UUID
    doctor_id: UUID | None = None
    order_number: str
    order_category: OrderCategory
    priority: OrderPriority
    scheduled_date: date | None = None
    clinical_notes: str | None = None
    status: OrderStatus
    created_at: datetime
    items: list[OrderItemRead] = Field(default_factory=list)


# --- Procedures ---

class ProcedureCreate(BaseModel):
    procedure_name: str = Field(min_length=1, max_length=255)
    procedure_date: date | None = None
    notes: str | None = None


class ProcedureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    visit_id: UUID
    doctor_id: UUID | None = None
    procedure_name: str
    procedure_date: date | None = None
    notes: str | None = None
    status: OrderStatus
    created_at: datetime


# --- Referrals ---

class ReferralCreate(BaseModel):
    referred_to: str = Field(min_length=1, max_length=255)
    reason: str | None = None
    notes: str | None = None


class ReferralRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    visit_id: UUID
    doctor_id: UUID | None = None
    referred_to: str
    reason: str | None = None
    notes: str | None = None
    status: OrderStatus
    created_at: datetime
    doctor_signature_snapshot_url: str | None = None


# --- Prescriptions ---

class PrescriptionItemCreate(BaseModel):
    medicine: str = Field(min_length=1, max_length=255)
    generic_name: str | None = None
    brand_name: str | None = None
    strength: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    duration: str | None = None
    quantity: str | None = None
    route: str | None = None
    instructions: str | None = None
    substitution_allowed: bool = True


class PrescriptionItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    medicine: str
    generic_name: str | None = None
    brand_name: str | None = None
    strength: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    duration: str | None = None
    quantity: str | None = None
    route: str | None = None
    instructions: str | None = None
    substitution_allowed: bool


class PrescriptionCreate(BaseModel):
    items: list[PrescriptionItemCreate] = Field(min_length=1)
    status: PrescriptionStatus = PrescriptionStatus.DRAFT


class PrescriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    consultation_id: UUID
    visit_id: UUID
    patient_id: UUID
    doctor_id: UUID | None = None
    prescription_number: str
    status: PrescriptionStatus
    created_at: datetime
    items: list[PrescriptionItemRead] = Field(default_factory=list)
    doctor_signature_snapshot_url: str | None = None


class PrescriptionCreateResponse(BaseModel):
    prescription: PrescriptionRead
    warnings: list[str] = Field(default_factory=list)
