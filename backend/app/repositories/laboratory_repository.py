"""Repository for Laboratory Orders/Results/Attachments/Templates (Phase 10).

Phase 2A (Structured Result Backend Foundation) adds LaboratoryReferenceRange
CRUD + resolution alongside the existing Order/Result/Attachment/Template
methods below, in the same repository class - matching this module's
existing "one repository for the whole Laboratory domain" convention rather
than introducing a separate repository class.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.laboratory_attachment import LaboratoryAttachment
from app.models.laboratory_order import LaboratoryOrder, LaboratoryOrderStatus
from app.models.laboratory_reference_range import LaboratoryReferenceRange
from app.models.laboratory_result import LaboratoryResult
from app.models.laboratory_template import LaboratoryTemplate, LaboratoryTemplateParameter
from app.models.order import Order, OrderPriority
from app.models.patient import Gender
from app.models.visit import Visit


def _order_options():
    return (
        selectinload(LaboratoryOrder.order),
        selectinload(LaboratoryOrder.visit).selectinload(Visit.queue),
        selectinload(LaboratoryOrder.patient),
        selectinload(LaboratoryOrder.doctor),
        selectinload(LaboratoryOrder.template).selectinload(LaboratoryTemplate.parameters),
        selectinload(LaboratoryOrder.results),
        selectinload(LaboratoryOrder.attachments),
    )


class LaboratoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # --- Laboratory Orders ---

    async def create_laboratory_order(self, **fields) -> LaboratoryOrder:
        lab_order = LaboratoryOrder(**fields)
        self.session.add(lab_order)
        await self.session.flush()
        await self.session.refresh(lab_order, attribute_names=["order", "visit", "patient", "doctor", "template", "results", "attachments"])
        if lab_order.visit is not None:
            await self.session.refresh(lab_order.visit, attribute_names=["queue"])
        return lab_order

    async def get_by_id(self, laboratory_order_id: UUID, clinic_id: UUID) -> LaboratoryOrder | None:
        stmt = (
            select(LaboratoryOrder)
            .where(LaboratoryOrder.id == laboratory_order_id, LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False))
            .options(*_order_options())
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_order_id(self, order_id: UUID, clinic_id: UUID) -> LaboratoryOrder | None:
        stmt = (
            select(LaboratoryOrder)
            .where(LaboratoryOrder.order_id == order_id, LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False))
            .options(*_order_options())
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_for_clinic(self, clinic_id: UUID, *, status: LaboratoryOrderStatus | None = None) -> list[LaboratoryOrder]:
        filters = [LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False)]
        if status is not None:
            filters.append(LaboratoryOrder.status == status)
        stmt = select(LaboratoryOrder).where(*filters).options(*_order_options()).order_by(LaboratoryOrder.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_visit(self, visit_id: UUID, clinic_id: UUID) -> list[LaboratoryOrder]:
        stmt = (
            select(LaboratoryOrder)
            .where(LaboratoryOrder.visit_id == visit_id, LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False))
            .options(*_order_options())
            .order_by(LaboratoryOrder.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_for_patient(self, patient_id: UUID, clinic_id: UUID) -> list[LaboratoryOrder]:
        stmt = (
            select(LaboratoryOrder)
            .where(LaboratoryOrder.patient_id == patient_id, LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False))
            .options(*_order_options())
            .order_by(LaboratoryOrder.created_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_laboratory_order(self, lab_order: LaboratoryOrder, **fields) -> LaboratoryOrder:
        for key, value in fields.items():
            setattr(lab_order, key, value)
        await self.session.flush()
        return lab_order

    async def dashboard_counts(self, clinic_id: UUID, *, today: date) -> dict:
        stmt = select(LaboratoryOrder.status, LaboratoryOrder.completed_at, LaboratoryOrder.order_id).where(
            LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False)
        )
        rows = (await self.session.execute(stmt)).all()
        counts = {"pending": 0, "collected": 0, "processing": 0, "completed_today": 0, "cancelled": 0}
        order_ids = []
        for status_val, completed_at, order_id in rows:
            if status_val == LaboratoryOrderStatus.REQUESTED:
                counts["pending"] += 1
            elif status_val == LaboratoryOrderStatus.COLLECTED:
                counts["collected"] += 1
            elif status_val == LaboratoryOrderStatus.PROCESSING:
                counts["processing"] += 1
            elif status_val == LaboratoryOrderStatus.CANCELLED:
                counts["cancelled"] += 1
            if completed_at is not None and completed_at.date() == today:
                counts["completed_today"] += 1
            order_ids.append(order_id)

        stat_count = 0
        if order_ids:
            stat_stmt = select(func.count()).select_from(Order).where(Order.id.in_(order_ids), Order.priority == OrderPriority.STAT)
            stat_count = (await self.session.execute(stat_stmt)).scalar_one()
        counts["stat_orders"] = stat_count
        return counts

    # --- Phase 12: Owner Dashboard & Reports (Laboratory Reports) ---

    async def count_created_in_range(self, clinic_id: UUID, dt_from, dt_to) -> int:
        stmt = select(func.count()).select_from(LaboratoryOrder).where(
            LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False),
            LaboratoryOrder.created_at >= dt_from, LaboratoryOrder.created_at < dt_to,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def report_counts_in_range(self, clinic_id: UUID, dt_from, dt_to) -> dict:
        stmt = select(LaboratoryOrder.status, func.count()).where(
            LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False),
            LaboratoryOrder.created_at >= dt_from, LaboratoryOrder.created_at < dt_to,
        ).group_by(LaboratoryOrder.status)
        rows = (await self.session.execute(stmt)).all()
        return {r[0].value: int(r[1]) for r in rows}

    async def avg_turnaround_seconds(self, clinic_id: UUID, dt_from, dt_to) -> float | None:
        from sqlalchemy import extract

        duration = extract("epoch", LaboratoryOrder.completed_at - LaboratoryOrder.created_at)
        stmt = select(func.avg(duration)).where(
            LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False),
            LaboratoryOrder.completed_at.is_not(None),
            LaboratoryOrder.created_at >= dt_from, LaboratoryOrder.created_at < dt_to,
        )
        val = (await self.session.execute(stmt)).scalar_one()
        return float(val) if val is not None else None

    async def top_requested_tests(self, clinic_id: UUID, dt_from, dt_to, limit: int = 10) -> list[dict]:
        stmt = (
            select(LaboratoryOrder.test_type, func.count())
            .where(
                LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False),
                LaboratoryOrder.created_at >= dt_from, LaboratoryOrder.created_at < dt_to,
            )
            .group_by(LaboratoryOrder.test_type)
            .order_by(func.count().desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"test": r[0], "value": int(r[1])} for r in rows]

    async def daily_volume_series(self, clinic_id: UUID, dt_from, dt_to) -> list[dict]:
        day_col = func.date(LaboratoryOrder.created_at)
        stmt = (
            select(day_col, func.count())
            .where(
                LaboratoryOrder.clinic_id == clinic_id, LaboratoryOrder.is_deleted.is_(False),
                LaboratoryOrder.created_at >= dt_from, LaboratoryOrder.created_at < dt_to,
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        rows = (await self.session.execute(stmt)).all()
        return [{"date": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]), "value": int(r[1])} for r in rows]

    # --- Results ---

    async def upsert_results(self, laboratory_order_id: UUID, clinic_id: UUID, results: list[dict], *, actor_id) -> list[LaboratoryResult]:
        """Replace-all semantics: a result-entry submission for an order
        represents the full current parameter set (matches how the
        Result Entry UI pre-populates all template parameters and lets the
        user edit/add rows), so existing rows are deleted and replaced
        rather than merged field-by-field - simpler and avoids stale rows
        for parameters removed from a resubmission."""
        existing_stmt = select(LaboratoryResult).where(
            LaboratoryResult.laboratory_order_id == laboratory_order_id, LaboratoryResult.clinic_id == clinic_id
        )
        existing = (await self.session.execute(existing_stmt)).scalars().all()
        for row in existing:
            await self.session.delete(row)
        await self.session.flush()

        created = []
        for r in results:
            result = LaboratoryResult(
                clinic_id=clinic_id, laboratory_order_id=laboratory_order_id, entered_by=actor_id, **r
            )
            self.session.add(result)
            created.append(result)
        await self.session.flush()
        return created

    # --- Attachments ---

    async def add_attachment(self, **fields) -> LaboratoryAttachment:
        attachment = LaboratoryAttachment(**fields)
        self.session.add(attachment)
        await self.session.flush()
        return attachment

    async def list_attachments(self, laboratory_order_id: UUID, clinic_id: UUID) -> list[LaboratoryAttachment]:
        stmt = select(LaboratoryAttachment).where(
            LaboratoryAttachment.laboratory_order_id == laboratory_order_id,
            LaboratoryAttachment.clinic_id == clinic_id,
            LaboratoryAttachment.is_deleted.is_(False),
        ).order_by(LaboratoryAttachment.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_attachment(self, attachment_id: UUID, laboratory_order_id: UUID, clinic_id: UUID) -> LaboratoryAttachment | None:
        stmt = select(LaboratoryAttachment).where(
            LaboratoryAttachment.id == attachment_id,
            LaboratoryAttachment.laboratory_order_id == laboratory_order_id,
            LaboratoryAttachment.clinic_id == clinic_id,
            LaboratoryAttachment.is_deleted.is_(False),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # --- Templates ---

    async def create_template(self, *, parameters: list[dict], **fields) -> LaboratoryTemplate:
        template = LaboratoryTemplate(**fields)
        self.session.add(template)
        await self.session.flush()
        for i, p in enumerate(parameters):
            p.setdefault("display_order", i)
            self.session.add(LaboratoryTemplateParameter(template_id=template.id, clinic_id=template.clinic_id, **p))
        await self.session.flush()
        await self.session.refresh(template, attribute_names=["parameters"])
        return template

    async def get_template(self, template_id: UUID, clinic_id: UUID) -> LaboratoryTemplate | None:
        stmt = (
            select(LaboratoryTemplate)
            .where(LaboratoryTemplate.id == template_id, LaboratoryTemplate.clinic_id == clinic_id, LaboratoryTemplate.is_deleted.is_(False))
            .options(selectinload(LaboratoryTemplate.parameters))
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_template_any_clinic(self, template_id: UUID) -> LaboratoryTemplate | None:
        """Deliberately NOT clinic-scoped - used only by Import preview/
        commit to tell "this ID doesn't exist anywhere" apart from "this ID
        belongs to a different clinic", so cross-tenant import attempts get
        a clear rejection reason instead of a generic 404. Never used to
        read or return another clinic's data to the caller - only whether
        a row with this id exists and, if so, its `clinic_id`."""
        stmt = select(LaboratoryTemplate).where(
            LaboratoryTemplate.id == template_id, LaboratoryTemplate.is_deleted.is_(False)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_templates(self, clinic_id: UUID, *, active_only: bool = False) -> list[LaboratoryTemplate]:
        filters = [LaboratoryTemplate.clinic_id == clinic_id, LaboratoryTemplate.is_deleted.is_(False)]
        if active_only:
            filters.append(LaboratoryTemplate.is_active.is_(True))
        stmt = select(LaboratoryTemplate).where(*filters).options(selectinload(LaboratoryTemplate.parameters)).order_by(LaboratoryTemplate.test_name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_template(self, template: LaboratoryTemplate, *, parameters: list[dict] | None = None, **fields) -> LaboratoryTemplate:
        for key, value in fields.items():
            setattr(template, key, value)
        if parameters is not None:
            for existing in list(template.parameters):
                await self.session.delete(existing)
            await self.session.flush()
            for i, p in enumerate(parameters):
                p.setdefault("display_order", i)
                self.session.add(LaboratoryTemplateParameter(template_id=template.id, clinic_id=template.clinic_id, **p))
        await self.session.flush()
        await self.session.refresh(template, attribute_names=["parameters"])
        return template

    # --- Reference Ranges (Phase 2A) ---

    async def create_reference_range(self, **fields) -> LaboratoryReferenceRange:
        reference_range = LaboratoryReferenceRange(**fields)
        self.session.add(reference_range)
        await self.session.flush()
        await self.session.refresh(reference_range)
        return reference_range

    async def get_reference_range(self, reference_range_id: UUID, clinic_id: UUID) -> LaboratoryReferenceRange | None:
        stmt = select(LaboratoryReferenceRange).where(
            LaboratoryReferenceRange.id == reference_range_id,
            LaboratoryReferenceRange.clinic_id == clinic_id,
            LaboratoryReferenceRange.is_deleted.is_(False),
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_reference_ranges_for_parameter(
        self, template_parameter_id: UUID, clinic_id: UUID, *, active_only: bool = False
    ) -> list[LaboratoryReferenceRange]:
        filters = [
            LaboratoryReferenceRange.template_parameter_id == template_parameter_id,
            LaboratoryReferenceRange.clinic_id == clinic_id,
            LaboratoryReferenceRange.is_deleted.is_(False),
        ]
        if active_only:
            filters.append(LaboratoryReferenceRange.is_active.is_(True))
        stmt = select(LaboratoryReferenceRange).where(*filters).order_by(LaboratoryReferenceRange.effective_from.desc().nulls_last())
        return list((await self.session.execute(stmt)).scalars().all())

    async def update_reference_range(self, reference_range: LaboratoryReferenceRange, **fields) -> LaboratoryReferenceRange:
        for key, value in fields.items():
            setattr(reference_range, key, value)
        await self.session.flush()
        await self.session.refresh(reference_range)
        return reference_range

    async def resolve_reference_range(
        self, template_parameter_id: UUID, clinic_id: UUID, *, sex: Gender | None, age_years: int | None
    ) -> LaboratoryReferenceRange | None:
        """Future-precedence lookup (Phase 2A foundation, not yet wired into
        the live result-entry path - see laboratory_service.py). Returns the
        most specific active row whose sex/age bounds match the given
        patient demographics, or None if no row matches (caller falls back
        to the template parameter's own default range_low/range_high/
        expected_normal_text - see `LaboratoryService.
        resolve_reference_range_for_patient`).

        "Most specific" = most non-null demographic filters set, narrowest
        first (mirrors `QueueSettingRepository.get_effective_for_doctor`'s
        narrowest-scope-wins precedence); ties broken by most recent
        `effective_from`."""
        candidates = await self.list_reference_ranges_for_parameter(template_parameter_id, clinic_id, active_only=True)

        def matches(r: LaboratoryReferenceRange) -> bool:
            if r.sex is not None and r.sex != sex:
                return False
            if r.age_min_years is not None and (age_years is None or age_years < r.age_min_years):
                return False
            if r.age_max_years is not None and (age_years is None or age_years > r.age_max_years):
                return False
            return True

        def specificity(r: LaboratoryReferenceRange) -> int:
            return sum(1 for v in (r.sex, r.age_min_years, r.age_max_years) if v is not None)

        matching = [r for r in candidates if matches(r)]
        if not matching:
            return None
        matching.sort(key=lambda r: (specificity(r), r.effective_from or date.min), reverse=True)
        return matching[0]
