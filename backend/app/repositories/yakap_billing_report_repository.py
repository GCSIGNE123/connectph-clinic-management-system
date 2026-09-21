"""Queries for the YAKAP Billing Report (Task #4).

Report population (business decision, Task #4): invoices of patients whose
STANDING flag `Patient.is_yakap_beneficiary` is true. `Queue.visit_classification`
is deliberately NOT consulted anywhere in this module - the two YAKAP
concepts stay independent. Reporting date basis: `Invoice.invoice_date`
(already Asia/Manila-based since Task #9). Cancelled and Draft invoices are
not billable and are excluded, matching the Billing page's status set.

Every query is clinic-scoped and aggregates in SQL; the caller never sums
rows client-side.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus
from app.models.invoice_item import InvoiceItem, InvoiceItemType
from app.models.patient import Patient
from app.models.payment import Payment, PaymentStatus
from app.models.visit import Visit

EXCLUDED_STATUSES = (InvoiceStatus.CANCELLED, InvoiceStatus.DRAFT)
CONSULTATION_ITEM_TYPES = (InvoiceItemType.CONSULTATION_FEE,)
ZERO = Decimal("0")


class YakapBillingReportRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _filters(self, clinic_id: UUID, date_from: date, date_to: date, q: str | None):
        filters = [
            Invoice.clinic_id == clinic_id,
            Invoice.is_deleted.is_(False),
            Invoice.status.notin_(EXCLUDED_STATUSES),
            Invoice.invoice_date >= date_from,
            Invoice.invoice_date <= date_to,
            Patient.clinic_id == clinic_id,
            Patient.is_deleted.is_(False),
            Patient.is_yakap_beneficiary.is_(True),
        ]
        if q:
            like = f"%{q.lower()}%"
            filters.append(
                or_(
                    func.lower(Invoice.invoice_number).like(like),
                    func.lower(Patient.patient_number).like(like),
                    func.lower(Patient.first_name).like(like),
                    func.lower(Patient.last_name).like(like),
                    func.lower(Visit.visit_number).like(like),
                )
            )
        return filters

    def _filtered_invoice_ids(self, clinic_id: UUID, date_from: date, date_to: date, q: str | None):
        return (
            select(Invoice.id)
            .join(Patient, Patient.id == Invoice.patient_id)
            .outerjoin(Visit, Visit.id == Invoice.visit_id)
            .where(and_(*self._filters(clinic_id, date_from, date_to, q)))
        )

    async def summary(self, clinic_id: UUID, date_from: date, date_to: date, q: str | None) -> dict:
        ids = self._filtered_invoice_ids(clinic_id, date_from, date_to, q).subquery()
        # Invoice-level totals: one row per invoice, so multi-item invoices are never multiplied.
        inv = (
            await self.session.execute(
                select(
                    func.count(Invoice.id),
                    func.count(func.distinct(Invoice.patient_id)),
                    func.coalesce(func.sum(Invoice.grand_total), ZERO),
                    func.coalesce(func.sum(Invoice.balance_due), ZERO),
                ).where(Invoice.id.in_(select(ids.c.id)))
            )
        ).one()
        paid = (
            await self.session.execute(
                select(func.coalesce(func.sum(Payment.amount), ZERO)).where(
                    Payment.clinic_id == clinic_id,
                    Payment.status == PaymentStatus.COMPLETED,
                    Payment.invoice_id.in_(select(ids.c.id)),
                )
            )
        ).scalar_one()
        item_counts = dict(
            (
                await self.session.execute(
                    select(InvoiceItem.item_type, func.count(InvoiceItem.id))
                    .where(InvoiceItem.clinic_id == clinic_id, InvoiceItem.invoice_id.in_(select(ids.c.id)))
                    .group_by(InvoiceItem.item_type)
                )
            ).all()
        )
        return {
            "total_invoices": int(inv[0]),
            "total_yakap_patients": int(inv[1]),
            "total_billed": Decimal(inv[2]),
            "total_outstanding": Decimal(inv[3]),
            "total_paid": Decimal(paid),
            "total_consultations": int(sum(item_counts.get(t, 0) for t in CONSULTATION_ITEM_TYPES)),
            "total_laboratory_services": int(item_counts.get(InvoiceItemType.LABORATORY, 0)),
        }

    async def page(
        self, clinic_id: UUID, date_from: date, date_to: date, q: str | None, *, limit: int | None, offset: int
    ) -> list[dict]:
        stmt = (
            select(Invoice, Patient, Visit)
            .join(Patient, Patient.id == Invoice.patient_id)
            .outerjoin(Visit, Visit.id == Invoice.visit_id)
            .where(and_(*self._filters(clinic_id, date_from, date_to, q)))
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc(), Invoice.id.desc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = (await self.session.execute(stmt)).all()
        if not rows:
            return []
        invoice_ids = [inv.id for inv, _p, _v in rows]

        paid_by_invoice = dict(
            (
                await self.session.execute(
                    select(Payment.invoice_id, func.coalesce(func.sum(Payment.amount), ZERO))
                    .where(
                        Payment.clinic_id == clinic_id,
                        Payment.status == PaymentStatus.COMPLETED,
                        Payment.invoice_id.in_(invoice_ids),
                    )
                    .group_by(Payment.invoice_id)
                )
            ).all()
        )
        items_by_invoice: dict[UUID, list[tuple]] = {}
        for invoice_id, item_type, description in (
            await self.session.execute(
                select(InvoiceItem.invoice_id, InvoiceItem.item_type, InvoiceItem.description)
                .where(InvoiceItem.clinic_id == clinic_id, InvoiceItem.invoice_id.in_(invoice_ids))
                .order_by(InvoiceItem.created_at, InvoiceItem.id)
            )
        ).all():
            items_by_invoice.setdefault(invoice_id, []).append((item_type, description))

        out = []
        for inv, patient, visit in rows:
            items = items_by_invoice.get(inv.id, [])
            out.append(
                {
                    "invoice_id": inv.id,
                    "invoice_number": inv.invoice_number,
                    "invoice_date": inv.invoice_date,
                    "patient_id": patient.id,
                    "patient_number": patient.patient_number,
                    "patient_name": " ".join(x for x in (patient.first_name, patient.last_name) if x),
                    "visit_id": visit.id if visit else None,
                    "visit_number": visit.visit_number if visit else None,
                    "consultation_count": sum(1 for t, _d in items if t in CONSULTATION_ITEM_TYPES),
                    "laboratory_count": sum(1 for t, _d in items if t == InvoiceItemType.LABORATORY),
                    "services": [d for _t, d in items],
                    "total_billed": Decimal(inv.grand_total),
                    "paid": Decimal(paid_by_invoice.get(inv.id, ZERO)),
                    "outstanding": Decimal(inv.balance_due),
                    "status": inv.status.value,
                }
            )
        return out

    async def count(self, clinic_id: UUID, date_from: date, date_to: date, q: str | None) -> int:
        ids = self._filtered_invoice_ids(clinic_id, date_from, date_to, q).subquery()
        return int((await self.session.execute(select(func.count()).select_from(ids))).scalar_one())
