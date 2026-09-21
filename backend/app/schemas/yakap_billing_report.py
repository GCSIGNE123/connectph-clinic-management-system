"""Schemas for the YAKAP Billing Report (Task #4)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class YakapReportSummary(BaseModel):
    """Aggregated over the ENTIRE filtered population (never over one page)."""

    total_yakap_patients: int
    total_invoices: int
    total_consultations: int
    total_laboratory_services: int
    total_billed: Decimal
    total_paid: Decimal
    total_outstanding: Decimal


class YakapReportRow(BaseModel):
    """One row per INVOICE (so an invoice with several services is never
    counted more than once); services are shown as a list, not extra rows."""

    invoice_id: UUID
    invoice_number: str
    invoice_date: date
    patient_id: UUID
    patient_number: str
    patient_name: str
    visit_id: UUID | None = None
    visit_number: str | None = None
    consultation_count: int
    laboratory_count: int
    services: list[str]
    total_billed: Decimal
    paid: Decimal
    outstanding: Decimal
    status: str


class YakapBillingReportResponse(BaseModel):
    period: str
    date_from: date
    date_to: date
    summary: YakapReportSummary
    items: list[YakapReportRow]
    total: int
    limit: int
    offset: int
