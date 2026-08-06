"""Repository for the Patient model: search/filter/sort/paginate and
duplicate-detection queries used by PatientService.
"""

from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient
from app.repositories.base import BaseRepository
from app.schemas.patient import PatientSearchParams


class PatientRepository(BaseRepository[Patient]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, model=Patient)

    async def get_by_id_and_clinic(self, id_: UUID, clinic_id: UUID) -> Patient | None:
        stmt = select(Patient).where(Patient.id == id_, Patient.clinic_id == clinic_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_patient_number(self, patient_number: str, clinic_id: UUID) -> Patient | None:
        stmt = select(Patient).where(
            Patient.clinic_id == clinic_id, Patient.patient_number == patient_number
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _base_filters(self, clinic_id: UUID, params: PatientSearchParams):
        filters = [Patient.clinic_id == clinic_id, Patient.is_deleted.is_(False)]

        if params.q:
            like = f"%{params.q.lower()}%"
            filters.append(
                or_(
                    func.lower(Patient.patient_number).like(like),
                    func.lower(func.coalesce(Patient.legacy_patient_id, "")).like(like),
                    func.lower(Patient.first_name).like(like),
                    func.lower(func.coalesce(Patient.middle_name, "")).like(like),
                    func.lower(Patient.last_name).like(like),
                    func.lower(Patient.mobile_number).like(like),
                    func.lower(func.coalesce(Patient.email, "")).like(like),
                )
            )

        if params.branch_id is not None:
            filters.append(Patient.branch_id == params.branch_id)
        if params.gender is not None:
            filters.append(Patient.gender == params.gender)
        if params.status is not None:
            filters.append(Patient.status == params.status)

        # Age range -> birth_date range (inclusive). age_min=older bound (earlier
        # birth_date), age_max=younger bound (later birth_date).
        today = date.today()
        if params.age_max is not None:
            earliest_birth_date = date(today.year - params.age_max - 1, today.month, today.day) + timedelta(days=1)
            filters.append(Patient.birth_date >= earliest_birth_date)
        if params.age_min is not None:
            latest_birth_date = date(today.year - params.age_min, today.month, today.day)
            filters.append(Patient.birth_date <= latest_birth_date)

        if params.registered_from is not None:
            filters.append(Patient.date_registered >= params.registered_from)
        if params.registered_to is not None:
            filters.append(Patient.date_registered <= params.registered_to)

        if params.last_visit_from is not None:
            filters.append(Patient.last_visit >= params.last_visit_from)
        if params.last_visit_to is not None:
            filters.append(Patient.last_visit <= params.last_visit_to)

        return filters

    def _apply_sort(self, stmt, sort: str):
        if sort == "oldest":
            return stmt.order_by(Patient.created_at.asc())
        if sort == "alphabetical":
            return stmt.order_by(Patient.last_name.asc(), Patient.first_name.asc())
        if sort == "recently_visited":
            return stmt.order_by(Patient.last_visit.desc().nulls_last(), Patient.created_at.desc())
        # default: newest
        return stmt.order_by(Patient.created_at.desc())

    async def search(
        self, clinic_id: UUID, params: PatientSearchParams
    ) -> tuple[list[Patient], int]:
        filters = self._base_filters(clinic_id, params)

        count_stmt = select(func.count()).select_from(Patient).where(and_(*filters))
        count_result = await self.session.execute(count_stmt)
        total = int(count_result.scalar_one())

        stmt = select(Patient).where(and_(*filters))
        stmt = self._apply_sort(stmt, params.sort)
        stmt = stmt.offset(params.offset).limit(params.limit)

        rows_result = await self.session.execute(stmt)
        return list(rows_result.scalars().all()), total

    async def find_duplicates(
        self,
        clinic_id: UUID,
        *,
        first_name: str,
        last_name: str,
        birth_date: date,
        mobile_number: str,
        exclude_id: UUID | None = None,
    ) -> list[tuple[Patient, str]]:
        """Return (patient, match_reason) pairs for likely-duplicate records.

        Two independent signals: (1) same first+last name and birth date, or
        (2) same mobile number. A record can match on both; the reason
        returned favors the name+DOB match when both apply.
        """
        name_dob_filters = [
            Patient.clinic_id == clinic_id,
            Patient.is_deleted.is_(False),
            func.lower(Patient.first_name) == first_name.lower(),
            func.lower(Patient.last_name) == last_name.lower(),
            Patient.birth_date == birth_date,
        ]
        mobile_filters = [
            Patient.clinic_id == clinic_id,
            Patient.is_deleted.is_(False),
            Patient.mobile_number == mobile_number,
        ]
        if exclude_id is not None:
            name_dob_filters.append(Patient.id != exclude_id)
            mobile_filters.append(Patient.id != exclude_id)

        name_dob_matches = list((await self.session.execute(select(Patient).where(and_(*name_dob_filters)))).scalars().all())
        mobile_matches = list((await self.session.execute(select(Patient).where(and_(*mobile_filters)))).scalars().all())

        reasons: dict[UUID, str] = {}
        by_id: dict[UUID, Patient] = {}
        for patient in name_dob_matches:
            by_id[patient.id] = patient
            reasons[patient.id] = "Same name and date of birth"
        for patient in mobile_matches:
            by_id.setdefault(patient.id, patient)
            reasons.setdefault(patient.id, "Same mobile number")

        return [(by_id[pid], reason) for pid, reason in reasons.items()]


    # --- Phase 12: Owner Dashboard & Reports ---

    async def count_created_in_range(self, clinic_id: UUID, dt_from: datetime, dt_to: datetime) -> int:
        """"New Patients Today"/"New Patients (period)": patients whose record was created within the window."""
        stmt = select(func.count()).select_from(Patient).where(
            Patient.clinic_id == clinic_id, Patient.created_at >= dt_from, Patient.created_at < dt_to,
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def gender_distribution(self, clinic_id: UUID, patient_ids: set[UUID] | None = None) -> dict[str, int]:
        filters = [Patient.clinic_id == clinic_id, Patient.is_deleted.is_(False)]
        if patient_ids is not None:
            if not patient_ids:
                return {}
            filters.append(Patient.id.in_(patient_ids))
        stmt = select(Patient.gender, func.count()).where(and_(*filters)).group_by(Patient.gender)
        rows = (await self.session.execute(stmt)).all()
        return {r[0].value: int(r[1]) for r in rows}

    async def age_distribution(self, clinic_id: UUID, patient_ids: set[UUID] | None = None) -> dict[str, int]:
        """Bucketed age distribution (0-12, 13-19, 20-39, 40-59, 60+), computed
        via a real SQL CASE expression over birth_date rather than fetching
        every row into Python."""
        from sqlalchemy import case, cast, Integer

        age_expr = cast(func.extract("year", func.age(func.current_date(), Patient.birth_date)), Integer)
        bucket = case(
            (age_expr < 13, "0-12"),
            (age_expr < 20, "13-19"),
            (age_expr < 40, "20-39"),
            (age_expr < 60, "40-59"),
            else_="60+",
        )
        filters = [Patient.clinic_id == clinic_id, Patient.is_deleted.is_(False)]
        if patient_ids is not None:
            if not patient_ids:
                return {}
            filters.append(Patient.id.in_(patient_ids))
        stmt = select(bucket, func.count()).where(and_(*filters)).group_by(bucket)
        rows = (await self.session.execute(stmt)).all()
        return {r[0]: int(r[1]) for r in rows}
