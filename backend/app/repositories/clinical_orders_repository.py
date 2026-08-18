"""Repository for Orders/OrderItems/Procedures/Referrals/Prescriptions (Phase 9)."""

from uuid import UUID

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import Order, OrderItem
from app.models.prescription import Prescription, PrescriptionItem
from app.models.procedure import Procedure
from app.models.referral import Referral


class ClinicalOrdersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Orders ---

    async def create_order(self, *, items: list[dict], **fields) -> Order:
        order = Order(**fields)
        self.session.add(order)
        await self.session.flush()
        for item_fields in items:
            self.session.add(OrderItem(order_id=order.id, clinic_id=order.clinic_id, **item_fields))
        await self.session.flush()
        await self.session.refresh(order, attribute_names=["items", "doctor", "patient"])
        return order

    async def get_order(self, order_id: UUID, clinic_id: UUID) -> Order | None:
        stmt = (
            select(Order)
            .where(Order.id == order_id, Order.clinic_id == clinic_id, Order.is_deleted.is_(False))
            .options(selectinload(Order.items), selectinload(Order.doctor), selectinload(Order.patient))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_orders_for_consultation(self, consultation_id: UUID, clinic_id: UUID) -> list[Order]:
        stmt = (
            select(Order)
            .where(Order.consultation_id == consultation_id, Order.clinic_id == clinic_id, Order.is_deleted.is_(False))
            .options(selectinload(Order.items))
            .order_by(Order.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_orders_for_visit(self, visit_id: UUID, clinic_id: UUID, *, category=None) -> list[Order]:
        filters = [Order.visit_id == visit_id, Order.clinic_id == clinic_id, Order.is_deleted.is_(False)]
        if category is not None:
            filters.append(Order.order_category == category)
        stmt = select(Order).where(*filters).options(selectinload(Order.items)).order_by(Order.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_order(self, order: Order, **fields) -> Order:
        for key, value in fields.items():
            setattr(order, key, value)
        await self.session.flush()
        return order

    # --- Procedures ---

    async def create_procedure(self, **fields) -> Procedure:
        procedure = Procedure(**fields)
        self.session.add(procedure)
        await self.session.flush()
        return procedure

    async def list_procedures_for_consultation(self, consultation_id: UUID, clinic_id: UUID) -> list[Procedure]:
        stmt = select(Procedure).where(
            Procedure.consultation_id == consultation_id, Procedure.clinic_id == clinic_id, Procedure.is_deleted.is_(False)
        ).order_by(Procedure.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_procedures_for_visit(self, visit_id: UUID, clinic_id: UUID) -> list[Procedure]:
        stmt = select(Procedure).where(
            Procedure.visit_id == visit_id, Procedure.clinic_id == clinic_id, Procedure.is_deleted.is_(False)
        ).order_by(Procedure.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    # --- Referrals ---

    async def create_referral(self, **fields) -> Referral:
        referral = Referral(**fields)
        self.session.add(referral)
        await self.session.flush()
        return referral

    async def get_referral(self, referral_id: UUID, clinic_id: UUID) -> Referral | None:
        stmt = select(Referral).where(
            Referral.id == referral_id, Referral.clinic_id == clinic_id, Referral.is_deleted.is_(False)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_referrals_for_consultation(self, consultation_id: UUID, clinic_id: UUID) -> list[Referral]:
        stmt = select(Referral).where(
            Referral.consultation_id == consultation_id, Referral.clinic_id == clinic_id, Referral.is_deleted.is_(False)
        ).order_by(Referral.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_referrals_for_visit(self, visit_id: UUID, clinic_id: UUID) -> list[Referral]:
        stmt = select(Referral).where(
            Referral.visit_id == visit_id, Referral.clinic_id == clinic_id, Referral.is_deleted.is_(False)
        ).order_by(Referral.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    # --- Prescriptions ---

    async def create_prescription(self, *, items: list[dict], **fields) -> Prescription:
        prescription = Prescription(**fields)
        self.session.add(prescription)
        await self.session.flush()
        for item_fields in items:
            self.session.add(PrescriptionItem(prescription_id=prescription.id, clinic_id=prescription.clinic_id, **item_fields))
        await self.session.flush()
        await self.session.refresh(prescription, attribute_names=["items", "doctor", "patient"])
        return prescription

    async def get_prescription(self, prescription_id: UUID, clinic_id: UUID) -> Prescription | None:
        stmt = (
            select(Prescription)
            .where(Prescription.id == prescription_id, Prescription.clinic_id == clinic_id, Prescription.is_deleted.is_(False))
            .options(selectinload(Prescription.items), selectinload(Prescription.doctor), selectinload(Prescription.patient))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_prescriptions_for_consultation(self, consultation_id: UUID, clinic_id: UUID) -> list[Prescription]:
        stmt = (
            select(Prescription)
            .where(Prescription.consultation_id == consultation_id, Prescription.clinic_id == clinic_id, Prescription.is_deleted.is_(False))
            .options(selectinload(Prescription.items))
            .order_by(Prescription.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_prescriptions_for_visit(self, visit_id: UUID, clinic_id: UUID) -> list[Prescription]:
        stmt = (
            select(Prescription)
            .where(Prescription.visit_id == visit_id, Prescription.clinic_id == clinic_id, Prescription.is_deleted.is_(False))
            .options(selectinload(Prescription.items))
            .order_by(Prescription.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_prescriptions_for_patient(self, patient_id: UUID, clinic_id: UUID) -> list[Prescription]:
        stmt = (
            select(Prescription)
            .where(Prescription.patient_id == patient_id, Prescription.clinic_id == clinic_id, Prescription.is_deleted.is_(False))
            .options(selectinload(Prescription.items), selectinload(Prescription.doctor))
            .order_by(Prescription.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    # --- Phase 12: Owner Dashboard & Reports ---

    async def count_prescriptions_in_range(self, clinic_id: UUID, dt_from: datetime, dt_to: datetime) -> int:
        stmt = select(func.count()).select_from(Prescription).where(
            Prescription.clinic_id == clinic_id, Prescription.is_deleted.is_(False),
            Prescription.created_at >= dt_from, Prescription.created_at < dt_to,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def count_orders_by_category_in_range(self, clinic_id: UUID, dt_from: datetime, dt_to: datetime) -> dict[str, int]:
        stmt = (
            select(Order.order_category, func.count())
            .where(
                Order.clinic_id == clinic_id, Order.is_deleted.is_(False),
                Order.created_at >= dt_from, Order.created_at < dt_to,
            )
            .group_by(Order.order_category)
        )
        rows = (await self.session.execute(stmt)).all()
        return {r[0].value: int(r[1]) for r in rows}
