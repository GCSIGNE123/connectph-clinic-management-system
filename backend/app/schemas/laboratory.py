"""Pydantic schemas for Laboratory Management (Phase 10)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.laboratory_order import LaboratoryOrderStatus
from app.models.laboratory_result import LaboratoryInterpretation, LaboratoryResultType


# --- Templates ---

class LaboratoryTemplateParameterCreate(BaseModel):
    parameter_name: str = Field(min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=50)
    normal_range: str | None = Field(default=None, max_length=100)
    result_type: LaboratoryResultType = LaboratoryResultType.NUMERIC
    display_order: int = 0


class LaboratoryTemplateParameterRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parameter_name: str
    unit: str | None = None
    normal_range: str | None = None
    result_type: LaboratoryResultType
    display_order: int


class LaboratoryTemplateCreate(BaseModel):
    test_name: str = Field(min_length=1, max_length=255)
    test_category: str | None = Field(default=None, max_length=100)
    specimen_type: str | None = Field(default=None, max_length=100)
    default_price: Decimal = Decimal("0")
    turnaround_time_hours: int | None = None
    is_active: bool = True
    parameters: list[LaboratoryTemplateParameterCreate] = Field(default_factory=list)


class LaboratoryTemplateUpdate(BaseModel):
    test_name: str | None = Field(default=None, min_length=1, max_length=255)
    test_category: str | None = Field(default=None, max_length=100)
    specimen_type: str | None = Field(default=None, max_length=100)
    default_price: Decimal | None = None
    turnaround_time_hours: int | None = None
    is_active: bool | None = None
    parameters: list[LaboratoryTemplateParameterCreate] | None = None


class LaboratoryTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    test_name: str
    test_category: str | None = None
    specimen_type: str | None = None
    default_price: Decimal
    turnaround_time_hours: int | None = None
    is_active: bool
    parameters: list[LaboratoryTemplateParameterRead] = Field(default_factory=list)
    created_at: datetime


# --- Results ---

class LaboratoryResultInput(BaseModel):
    parameter_name: str = Field(min_length=1, max_length=255)
    result_type: LaboratoryResultType = LaboratoryResultType.NUMERIC
    numeric_value: Decimal | None = None
    text_value: str | None = None
    normal_range: str | None = Field(default=None, max_length=100)
    units: str | None = Field(default=None, max_length=50)
    interpretation: LaboratoryInterpretation | None = None
    remarks: str | None = None


class LaboratoryResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    parameter_name: str
    result_type: LaboratoryResultType
    numeric_value: Decimal | None = None
    text_value: str | None = None
    normal_range: str | None = None
    units: str | None = None
    interpretation: LaboratoryInterpretation | None = None
    remarks: str | None = None
    entered_by: UUID | None = None
    entered_at: datetime | None = None


class LaboratoryResultsSubmit(BaseModel):
    results: list[LaboratoryResultInput] = Field(min_length=1)


# --- Attachments ---

class LaboratoryAttachmentCreate(BaseModel):
    attachment_type: str
    file_name: str = Field(min_length=1, max_length=255)
    file_size_bytes: int | None = None


class LaboratoryAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attachment_type: str
    file_name: str
    file_url: str
    file_size_bytes: int | None = None
    uploaded_by: UUID | None = None
    created_at: datetime


# --- Orders ---

class LaboratoryOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    order_number: str | None = None
    visit_id: UUID
    visit_number: str | None = None
    patient_id: UUID
    patient_name: str | None = None
    doctor_id: UUID | None = None
    doctor_name: str | None = None
    template_id: UUID | None = None
    test_type: str
    priority: str | None = None
    status: LaboratoryOrderStatus
    scheduled_date: str | None = None
    collected_at: datetime | None = None
    collected_by: UUID | None = None
    processing_started_at: datetime | None = None
    completed_at: datetime | None = None
    released_at: datetime | None = None
    released_by: UUID | None = None
    invoice_item_id: UUID | None = None
    created_at: datetime
    results: list[LaboratoryResultRead] = Field(default_factory=list)
    attachments: list[LaboratoryAttachmentRead] = Field(default_factory=list)


class LaboratoryDashboardStats(BaseModel):
    pending: int
    collected: int
    processing: int
    completed_today: int
    stat_orders: int
    cancelled: int
