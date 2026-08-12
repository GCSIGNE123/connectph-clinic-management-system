"""Shift service (Phase 21: Receptionist Shift Management).

Summary figures are always computed at read time from `Payment`/
`Discount`/`Refund` rows created within the shift's `opened_at`..(`closed_at`
or now) window, scoped to the receptionist who received the payment
(`Payment.received_by`) - the only cleanly-attributable field on that model
for "who processed this collection". `Discount.approved_by` and
`Refund.approved_by` track the *approver*, not necessarily the front-desk
receptionist who ran the register, so discount/refund totals are scoped to
clinic+branch+time-window instead of per-receptionist - read `Payment`,
`Discount`, `Refund` for exactly why before changing this.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discount import Discount
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentMethod, PaymentStatus, Refund
from app.models.shift import Shift, ShiftStatus
from app.models.user import User
from app.schemas.shift import ShiftClose, ShiftCreate, ShiftDetail, ShiftRead, ShiftSummary
from app.services.audit_service import AuditService
from app.services import sync_queue_service


SHIFT_ENFORCED_ROLE = "Receptionist"
SHIFT_REQUIRED_MESSAGE = "Please start your shift before serving patients."


async def enforce_receptionist_open_shift(session: AsyncSession, *, clinic_id: UUID, actor_id: UUID) -> None:
    """Item 7 (Shift Enforcement): shared gate called from
    `QueueService.create_queue` (which also covers
    `AppointmentService.check_in_appointment`, since check-in delegates to
    `create_queue`), and `PaymentService.record_payment`. Deliberately
    scoped to the Receptionist role only - Owner/Administrator (front-desk
    coverage) and Cashier (payment-only role) are NOT subject to this gate,
    per the client's explicit "this is a Receptionist workflow gate, not a
    blanket rule" instruction. Raises before any DB write happens in the
    caller, so a blocked attempt never creates partial state.

    Takes `actor_id` (not a `User` object) and re-fetches with
    `selectinload(User.role)` rather than trusting the caller's `actor.role`
    to already be eager-loaded - some call sites (`PaymentService`) only
    carry an `actor_id` UUID to begin with, and relying on lazy-load of
    `.role` under asyncio would raise `MissingGreenlet`.
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    stmt = select(User).options(selectinload(User.role)).where(User.id == actor_id)
    actor = (await session.execute(stmt)).scalar_one_or_none()
    role_name = actor.role.name if actor is not None and actor.role is not None else None
    if role_name != SHIFT_ENFORCED_ROLE:
        return
    has_open = await ShiftService(session).has_open_shift(clinic_id=clinic_id, user_id=actor_id)
    if not has_open:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=SHIFT_REQUIRED_MESSAGE)


class ShiftService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_service = AuditService(session)

    async def _get_or_404(self, shift_id: UUID, clinic_id: UUID) -> Shift:
        shift = await self.session.get(Shift, shift_id)
        if shift is None or shift.clinic_id != clinic_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift not found")
        return shift

    def _check_owns_or_admin(self, shift: Shift, actor: User) -> None:
        if actor.role is not None and actor.role.name in ("Owner", "Administrator"):
            return
        if shift.receptionist_user_id != actor.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action.")

    async def _to_read(self, shift: Shift) -> ShiftRead:
        receptionist = await self.session.get(User, shift.receptionist_user_id)
        return ShiftRead(
            id=shift.id, clinic_id=shift.clinic_id, branch_id=shift.branch_id,
            receptionist_user_id=shift.receptionist_user_id,
            receptionist_name=receptionist.full_name if receptionist is not None else None,
            opening_cash=shift.opening_cash, opened_at=shift.opened_at, closed_at=shift.closed_at,
            actual_cash_count=shift.actual_cash_count, status=shift.status, notes=shift.notes,
            created_at=shift.created_at, updated_at=shift.updated_at,
        )

    async def _compute_summary(self, shift: Shift) -> ShiftSummary:
        window_end = shift.closed_at or datetime.now(UTC)

        # Payments: scoped to this receptionist's own recorded collections
        # (Payment.received_by), within the shift window, excluding voided.
        payment_stmt = (
            select(Payment)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                Invoice.clinic_id == shift.clinic_id,
                Payment.received_by == shift.receptionist_user_id,
                Payment.status == PaymentStatus.COMPLETED,
                Payment.paid_at >= shift.opened_at,
                Payment.paid_at <= window_end,
            )
        )
        payments = (await self.session.execute(payment_stmt)).scalars().all()

        cash = gcash = card = other = Decimal("0")
        for p in payments:
            if p.payment_method == PaymentMethod.CASH:
                cash += p.amount
            elif p.payment_method == PaymentMethod.GCASH:
                gcash += p.amount
            elif p.payment_method in (PaymentMethod.CREDIT_CARD, PaymentMethod.DEBIT_CARD):
                card += p.amount
            else:
                other += p.amount
        total_collections = cash + gcash + card + other

        # Discounts/Refunds are not cleanly attributable to a single
        # receptionist on the existing models (no "recorded_by" field), so
        # these are scoped to clinic+branch+time-window instead.
        discount_stmt = (
            select(Discount)
            .join(Invoice, Invoice.id == Discount.invoice_id)
            .where(
                Invoice.clinic_id == shift.clinic_id,
                Discount.created_at >= shift.opened_at,
                Discount.created_at <= window_end,
            )
        )
        if shift.branch_id is not None:
            discount_stmt = discount_stmt.where(Invoice.branch_id == shift.branch_id)
        discounts = (await self.session.execute(discount_stmt)).scalars().all()
        discounts_given = sum((d.amount for d in discounts), Decimal("0"))

        refund_stmt = (
            select(Refund, Payment)
            .join(Payment, Payment.id == Refund.payment_id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(
                Invoice.clinic_id == shift.clinic_id,
                Refund.created_at >= shift.opened_at,
                Refund.created_at <= window_end,
                Refund.status == "Approved",
            )
        )
        if shift.branch_id is not None:
            refund_stmt = refund_stmt.where(Invoice.branch_id == shift.branch_id)
        refund_rows = (await self.session.execute(refund_stmt)).all()
        cash_refunds = Decimal("0")
        non_cash_refunds = Decimal("0")
        for refund, payment in refund_rows:
            if payment.payment_method == PaymentMethod.CASH:
                cash_refunds += refund.amount
            else:
                non_cash_refunds += refund.amount
        total_refunds = cash_refunds + non_cash_refunds

        expected_cash = shift.opening_cash + cash - cash_refunds

        return ShiftSummary(
            cash_collections=cash, gcash_collections=gcash, card_collections=card, other_collections=other,
            total_collections=total_collections, discounts_given=discounts_given,
            cash_refunds=cash_refunds, non_cash_refunds=non_cash_refunds, total_refunds=total_refunds,
            payment_count=len(payments), discount_count=len(discounts), refund_count=len(refund_rows),
            expected_cash=expected_cash,
        )

    async def _to_detail(self, shift: Shift) -> ShiftDetail:
        read = await self._to_read(shift)
        summary = await self._compute_summary(shift)
        cash_difference = None
        if shift.status == ShiftStatus.CLOSED and shift.actual_cash_count is not None:
            cash_difference = shift.actual_cash_count - summary.expected_cash
        return ShiftDetail(**read.model_dump(), summary=summary, expected_cash=summary.expected_cash, cash_difference=cash_difference)

    async def start_shift(self, payload: ShiftCreate, *, clinic_id: UUID, actor: User) -> ShiftDetail:
        existing_stmt = select(Shift).where(
            Shift.clinic_id == clinic_id,
            Shift.receptionist_user_id == actor.id,
            Shift.status == ShiftStatus.OPEN,
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an open shift. Close it before starting a new one.",
            )

        shift = Shift(
            clinic_id=clinic_id, branch_id=payload.branch_id, receptionist_user_id=actor.id,
            opening_cash=payload.opening_cash, opened_at=datetime.now(UTC), status=ShiftStatus.OPEN,
        )
        self.session.add(shift)
        await self.session.flush()

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="shift.opened",
            entity_type="shift", entity_id=str(shift.id),
            metadata={"opening_cash": str(payload.opening_cash)},
        )
        detail = await self._to_detail(shift)
        # Post-RC1 Phase 2 Milestone 2: Cloud Backup - best-effort (see
        # sync_queue_service.py). Note: unlike the other hooked services,
        # ShiftService relies on the request-scoped session's own
        # commit-on-success (`app/db/session.py::get_session`) rather than
        # calling `session.commit()` itself - nothing else happens in this
        # request after this point, so enqueuing here is equivalent in
        # practice.
        await sync_queue_service.enqueue(
            entity_type="shift", record_id=shift.id, operation="create",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail

    async def has_open_shift(self, *, clinic_id: UUID, user_id: UUID) -> bool:
        """Item 7 (Shift Enforcement): reusable "does this user have a
        currently-Open shift" check, shared by the Queue/Check-in/Payment
        enforcement points instead of each reimplementing the query."""
        stmt = select(Shift.id).where(
            Shift.clinic_id == clinic_id,
            Shift.receptionist_user_id == user_id,
            Shift.status == ShiftStatus.OPEN,
        )
        result = (await self.session.execute(stmt)).first()
        return result is not None

    async def get_current(self, *, clinic_id: UUID, actor: User) -> ShiftDetail | None:
        stmt = select(Shift).where(
            Shift.clinic_id == clinic_id,
            Shift.receptionist_user_id == actor.id,
            Shift.status == ShiftStatus.OPEN,
        )
        shift = (await self.session.execute(stmt)).scalar_one_or_none()
        if shift is None:
            return None
        return await self._to_detail(shift)

    async def get_shift(self, shift_id: UUID, *, clinic_id: UUID, actor: User) -> ShiftDetail:
        shift = await self._get_or_404(shift_id, clinic_id)
        self._check_owns_or_admin(shift, actor)
        return await self._to_detail(shift)

    async def close_shift(self, shift_id: UUID, payload: ShiftClose, *, clinic_id: UUID, actor: User) -> ShiftDetail:
        shift = await self._get_or_404(shift_id, clinic_id)
        self._check_owns_or_admin(shift, actor)
        if shift.status != ShiftStatus.OPEN:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift is not open.")

        shift.actual_cash_count = payload.actual_cash_count
        shift.closed_at = datetime.now(UTC)
        shift.status = ShiftStatus.CLOSED
        if payload.notes:
            shift.notes = payload.notes
        await self.session.flush()
        await self.session.refresh(shift)

        summary = await self._compute_summary(shift)
        cash_difference = payload.actual_cash_count - summary.expected_cash

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="shift.closed",
            entity_type="shift", entity_id=str(shift.id),
            metadata={
                "actual_cash_count": str(payload.actual_cash_count),
                "expected_cash": str(summary.expected_cash),
                "cash_difference": str(cash_difference),
            },
        )
        detail = await self._to_detail(shift)
        await sync_queue_service.enqueue(
            entity_type="shift", record_id=shift.id, operation="update",
            payload=detail.model_dump(mode="json"), clinic_id=clinic_id,
        )
        return detail

    async def reopen_shift(self, shift_id: UUID, *, clinic_id: UUID, actor: User) -> ShiftDetail:
        shift = await self._get_or_404(shift_id, clinic_id)
        if shift.status != ShiftStatus.CLOSED:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Shift is not closed.")

        # Reopening would collide with the "one Open shift per receptionist"
        # DB constraint if that receptionist already started a new one.
        existing_stmt = select(Shift).where(
            Shift.clinic_id == clinic_id,
            Shift.receptionist_user_id == shift.receptionist_user_id,
            Shift.status == ShiftStatus.OPEN,
        )
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Receptionist already has a different open shift; cannot reopen this one.",
            )

        shift.status = ShiftStatus.OPEN
        shift.closed_at = None
        shift.actual_cash_count = None
        await self.session.flush()
        await self.session.refresh(shift)

        await self.audit_service.log_event(
            clinic_id=clinic_id, user_id=actor.id, action="shift.reopened",
            entity_type="shift", entity_id=str(shift.id),
            metadata={"reopened_by_role": actor.role.name if actor.role is not None else None},
        )
        return await self._to_detail(shift)
