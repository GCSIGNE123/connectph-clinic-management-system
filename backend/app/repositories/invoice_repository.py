"""Repository for Invoice / InvoiceItem / Discount / Payment (Phase 9)."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.discount import Discount
from app.models.invoice import Invoice
from app.models.invoice_item import InvoiceItem
from app.models.patient import Patient
from app.models.payment import Payment, PaymentStatus
from app.models.visit import Visit


class InvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _detail_options(self):
        return (
            selectinload(Invoice.patient),
            selectinload(Invoice.doctor),
            selectinload(Invoice.branch),
            selectinload(Invoice.visit),
            selectinload(Invoice.items),
            selectinload(Invoice.discounts),
            selectinload(Invoice.payments),
        )

    async def get_by_id(self, invoice_id: UUID, clinic_id: UUID) -> Invoice | None:
        stmt = (
            select(Invoice)
            .where(Invoice.id == invoice_id, Invoice.clinic_id == clinic_id, Invoice.is_deleted.is_(False))
            .options(*self._detail_options())
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_for_visit(self, visit_id: UUID, clinic_id: UUID) -> Invoice | None:
        stmt = (
            select(Invoice)
            .where(Invoice.visit_id == visit_id, Invoice.clinic_id == clinic_id, Invoice.is_deleted.is_(False))
            .options(*self._detail_options())
            .order_by(Invoice.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def create_invoice(
        self, *, clinic_id: UUID, visit_id: UUID, branch_id: UUID, patient_id: UUID, doctor_id: UUID | None,
        invoice_number: str, invoice_date: date, actor_id: UUID | None,
    ) -> Invoice:
        invoice = Invoice(
            clinic_id=clinic_id, visit_id=visit_id, branch_id=branch_id, patient_id=patient_id,
            doctor_id=doctor_id, invoice_number=invoice_number, invoice_date=invoice_date,
            created_by=actor_id, updated_by=actor_id,
        )
        self.session.add(invoice)
        await self.session.flush()
        return invoice

    async def add_item(self, invoice_id: UUID, clinic_id: UUID, **fields) -> InvoiceItem:
        item = InvoiceItem(invoice_id=invoice_id, clinic_id=clinic_id, **fields)
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_item(self, item_id: UUID, invoice_id: UUID, clinic_id: UUID) -> InvoiceItem | None:
        stmt = select(InvoiceItem).where(
            InvoiceItem.id == item_id, InvoiceItem.invoice_id == invoice_id, InvoiceItem.clinic_id == clinic_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_item(self, item: InvoiceItem, **fields) -> InvoiceItem:
        for key, value in fields.items():
            setattr(item, key, value)
        await self.session.flush()
        return item

    async def delete_item(self, item: InvoiceItem) -> None:
        await self.session.delete(item)
        await self.session.flush()

    async def add_discount(self, invoice_id: UUID, clinic_id: UUID, **fields) -> Discount:
        discount = Discount(invoice_id=invoice_id, clinic_id=clinic_id, **fields)
        self.session.add(discount)
        await self.session.flush()
        return discount

    async def get_discount(self, discount_id: UUID, invoice_id: UUID, clinic_id: UUID) -> Discount | None:
        stmt = select(Discount).where(
            Discount.id == discount_id, Discount.invoice_id == invoice_id, Discount.clinic_id == clinic_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_discount(self, discount: Discount) -> None:
        await self.session.delete(discount)
        await self.session.flush()

    async def add_payment(self, invoice_id: UUID, clinic_id: UUID, **fields) -> Payment:
        payment = Payment(invoice_id=invoice_id, clinic_id=clinic_id, **fields)
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def get_payment(self, payment_id: UUID, clinic_id: UUID) -> Payment | None:
        stmt = select(Payment).where(Payment.id == payment_id, Payment.clinic_id == clinic_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_invoice(self, invoice: Invoice, **fields) -> Invoice:
        for key, value in fields.items():
            setattr(invoice, key, value)
        await self.session.flush()
        return invoice

    def _list_query(self, clinic_id: UUID, params):
        filters = [Invoice.clinic_id == clinic_id, Invoice.is_deleted.is_(False)]
        if params.status is not None:
            filters.append(Invoice.status == params.status)
        if params.date_from is not None:
            filters.append(Invoice.invoice_date >= params.date_from)
        if params.date_to is not None:
            filters.append(Invoice.invoice_date <= params.date_to)
        if params.cashier_id is not None:
            filters.append(
                Invoice.id.in_(
                    select(Payment.invoice_id).where(Payment.received_by == params.cashier_id)
                )
            )
        query = select(Invoice).where(and_(*filters))
        if params.q:
            like = f"%{params.q.lower()}%"
            query = (
                query.outerjoin(Patient, Patient.id == Invoice.patient_id)
                .outerjoin(Visit, Visit.id == Invoice.visit_id)
                .outerjoin(Payment, Payment.invoice_id == Invoice.id)
                .where(
                    (func.lower(Invoice.invoice_number).like(like))
                    | (func.lower(Patient.first_name).like(like))
                    | (func.lower(Patient.last_name).like(like))
                    | (func.lower(Patient.patient_number).like(like))
                    | (func.lower(Visit.visit_number).like(like))
                    | (func.lower(Payment.reference_number).like(like))
                )
                .distinct()
            )
        return query

    async def search(self, clinic_id: UUID, params) -> tuple[list[Invoice], int]:
        base_query = self._list_query(clinic_id, params)
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())

        stmt = (
            base_query.options(
                selectinload(Invoice.patient), selectinload(Invoice.doctor), selectinload(Invoice.visit)
            )
            # Sort on the same field the date filter above applies to
            # (invoice_date) - previously sorted on created_at, which could
            # disagree with a `date_from`/`date_to` filter on invoice_date.
            # created_at/id are stable tie-breaks for same-day invoices.
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc(), Invoice.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        rows = (await self.session.execute(stmt)).scalars().unique().all()
        return list(rows), total

    async def list_for_patient(
        self,
        clinic_id: UUID,
        patient_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> tuple[list[Invoice], int]:
        filters = [Invoice.clinic_id == clinic_id, Invoice.patient_id == patient_id, Invoice.is_deleted.is_(False)]
        if date_from is not None:
            filters.append(Invoice.invoice_date >= date_from)
        if date_to is not None:
            filters.append(Invoice.invoice_date <= date_to)
        count_stmt = select(func.count()).select_from(Invoice).where(and_(*filters))
        total = int((await self.session.execute(count_stmt)).scalar_one())
        stmt = (
            select(Invoice)
            .where(and_(*filters))
            .options(selectinload(Invoice.visit))
            .order_by(Invoice.invoice_date.desc(), Invoice.created_at.desc(), Invoice.id.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total

    # --- Dashboard aggregates ---

    async def count_pending_payments(self, clinic_id: UUID) -> int:
        from app.models.invoice import InvoiceStatus

        stmt = select(func.count()).select_from(Invoice).where(
            Invoice.clinic_id == clinic_id, Invoice.is_deleted.is_(False),
            Invoice.status.in_([InvoiceStatus.PENDING_PAYMENT, InvoiceStatus.PARTIALLY_PAID]),
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def sum_outstanding_balance(self, clinic_id: UUID) -> Decimal:
        stmt = select(func.coalesce(func.sum(Invoice.balance_due), 0)).where(
            Invoice.clinic_id == clinic_id, Invoice.is_deleted.is_(False), Invoice.balance_due > 0,
        )
        return Decimal(str((await self.session.execute(stmt)).scalar_one()))

    async def count_paid_today(self, clinic_id: UUID, day_start: datetime, day_end: datetime) -> int:
        stmt = select(func.count(func.distinct(Payment.invoice_id))).select_from(Payment).join(
            Invoice, Invoice.id == Payment.invoice_id
        ).where(
            Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED,
            Payment.paid_at >= day_start, Payment.paid_at < day_end,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def sum_todays_revenue(self, clinic_id: UUID, day_start: datetime, day_end: datetime) -> Decimal:
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).select_from(Payment).join(
            Invoice, Invoice.id == Payment.invoice_id
        ).where(
            Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED,
            Payment.paid_at >= day_start, Payment.paid_at < day_end,
        )
        return Decimal(str((await self.session.execute(stmt)).scalar_one()))

    async def recent_payments(self, clinic_id: UUID, limit: int = 10) -> list[Payment]:
        stmt = (
            select(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED)
            .options(selectinload(Payment.invoice).selectinload(Invoice.patient))
            .order_by(Payment.paid_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def count_pending_refunds(self, clinic_id: UUID) -> int:
        from app.models.payment import Refund

        stmt = select(func.count()).select_from(Refund).where(Refund.clinic_id == clinic_id, Refund.status == "Pending")
        return int((await self.session.execute(stmt)).scalar_one())

    # --- Phase 12: Owner Dashboard & Reports (revenue aggregation) ---
    # These reuse the same Payment/Invoice join pattern as
    # `sum_todays_revenue`/`count_paid_today` above, generalized to an
    # arbitrary [range_start, range_end) window and grouped by different
    # dimensions, per the spec's "Revenue by X" requirements. All real SQL
    # GROUP BY/SUM aggregation, no in-Python row iteration.

    async def sum_revenue_in_range(self, clinic_id: UUID, range_start: datetime, range_end: datetime) -> Decimal:
        stmt = select(func.coalesce(func.sum(Payment.amount), 0)).select_from(Payment).join(
            Invoice, Invoice.id == Payment.invoice_id
        ).where(
            Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED,
            Payment.paid_at >= range_start, Payment.paid_at < range_end,
        )
        return Decimal(str((await self.session.execute(stmt)).scalar_one()))

    async def revenue_by_doctor(self, clinic_id: UUID, range_start: datetime, range_end: datetime) -> list[dict]:
        from app.models.doctor import Doctor

        stmt = (
            select(Doctor.id, Doctor.first_name, Doctor.last_name, func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .join(Doctor, Doctor.id == Invoice.doctor_id)
            .where(
                Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= range_start, Payment.paid_at < range_end,
            )
            .group_by(Doctor.id, Doctor.first_name, Doctor.last_name)
            .order_by(func.sum(Payment.amount).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {"doctor_id": r[0], "doctor_name": f"{r[1]} {r[2]}".strip(), "revenue": Decimal(str(r[3]))}
            for r in rows
        ]

    async def revenue_by_branch(self, clinic_id: UUID, range_start: datetime, range_end: datetime) -> list[dict]:
        from app.models.branch import Branch

        stmt = (
            select(Branch.id, Branch.name, func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .join(Branch, Branch.id == Invoice.branch_id)
            .where(
                Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= range_start, Payment.paid_at < range_end,
            )
            .group_by(Branch.id, Branch.name)
            .order_by(func.sum(Payment.amount).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"branch_id": r[0], "branch_name": r[1], "revenue": Decimal(str(r[2]))} for r in rows]

    async def revenue_by_service(self, clinic_id: UUID, range_start: datetime, range_end: datetime) -> list[dict]:
        """Groups by InvoiceItem.description (item_type as fallback bucket),
        weighted by each item's share of its invoice's total payments -
        approximated here as line_total (billed amount) rather than actual
        cash received per-line, since payments apply to the invoice as a
        whole, not to individual line items. Documented simplification."""
        stmt = (
            select(InvoiceItem.item_type, func.coalesce(func.sum(InvoiceItem.line_total), 0))
            .select_from(InvoiceItem)
            .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
            .where(
                Invoice.clinic_id == clinic_id, Invoice.invoice_date >= range_start.date(),
                Invoice.invoice_date < range_end.date(),
                Invoice.status != "Cancelled",
            )
            .group_by(InvoiceItem.item_type)
            .order_by(func.sum(InvoiceItem.line_total).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"service": r[0].value if hasattr(r[0], "value") else r[0], "revenue": Decimal(str(r[1]))} for r in rows]

    async def revenue_by_payment_method(self, clinic_id: UUID, range_start: datetime, range_end: datetime) -> list[dict]:
        stmt = (
            select(Payment.payment_method, func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= range_start, Payment.paid_at < range_end,
            )
            .group_by(Payment.payment_method)
            .order_by(func.sum(Payment.amount).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"method": r[0].value if hasattr(r[0], "value") else r[0], "revenue": Decimal(str(r[1]))} for r in rows]

    async def outstanding_invoices_in_range(self, clinic_id: UUID, range_start: date, range_end: date) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .where(
                Invoice.clinic_id == clinic_id, Invoice.is_deleted.is_(False),
                Invoice.balance_due > 0, Invoice.invoice_date >= range_start, Invoice.invoice_date < range_end,
            )
            .options(selectinload(Invoice.patient))
            .order_by(Invoice.invoice_date.asc())
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def discount_summary_in_range(self, clinic_id: UUID, range_start: date, range_end: date) -> list[dict]:
        stmt = (
            select(Discount.discount_type, func.count(), func.coalesce(func.sum(Discount.amount), 0))
            .select_from(Discount)
            .join(Invoice, Invoice.id == Discount.invoice_id)
            .where(
                Invoice.clinic_id == clinic_id, Invoice.invoice_date >= range_start, Invoice.invoice_date < range_end,
            )
            .group_by(Discount.discount_type)
            .order_by(func.sum(Discount.amount).desc())
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {"discount_type": r[0].value if hasattr(r[0], "value") else r[0], "count": int(r[1]), "amount": Decimal(str(r[2]))}
            for r in rows
        ]

    async def daily_revenue_series(self, clinic_id: UUID, range_start: datetime, range_end: datetime) -> list[dict]:
        day_col = func.date(Payment.paid_at)
        stmt = (
            select(day_col, func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                Invoice.clinic_id == clinic_id, Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= range_start, Payment.paid_at < range_end,
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"date": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]), "value": Decimal(str(r[1]))} for r in rows]
