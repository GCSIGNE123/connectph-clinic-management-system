"""Laboratory Reference Ranges (Phase 2A - Structured Result Backend
Foundation).

Additive companion to `LaboratoryTemplateParameter.range_low`/`range_high`/
`expected_normal_text`, which remain untouched and continue to serve as the
default/fallback range for a parameter. A row here represents a
demographic-specific override (e.g. "Hemoglobin, Male, age 18-65") that
future result-entry/interpretation code can prefer over the parameter's
default when the patient matches - see
`LaboratoryRepository.resolve_reference_range` and
`LaboratoryService.resolve_reference_range_for_patient`.

Versioning follows the same soft-delete-adjacent convention used elsewhere
in this codebase (e.g. `DoctorSchedule`'s `is_active`/`effective_from`):
superseding a range does not delete or mutate the old row - it is set
`is_active=False` and a new row is inserted. `LaboratoryResult` already
denormalizes `range_low`/`range_high` onto itself at submission time (see
`laboratory_result.py`), so a historical result's applicable range is
never affected by a later change here, active or not.

`sex=None` means "applies regardless of sex" (deliberately not a third enum
member on `Gender`, which is Patient's own domain - see `Gender` reuse
below). `age_min_years`/`age_max_years=None` means "no lower/upper bound".

`critical_low`/`critical_high` are optional and, per Phase 2A's explicit
scope, are never pre-populated with clinical values by this codebase -
REQUIRES LABORATORY/CLINICAL VALIDATION before any clinic configures them.
"""

import enum
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.patient import Gender


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LaboratoryReferenceRange(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, Base):
    __tablename__ = "laboratory_reference_ranges"

    template_parameter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("laboratory_template_parameters.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sex: Mapped[Gender | None] = mapped_column(
        SAEnum(Gender, name="laboratory_reference_range_sex", values_callable=_enum_values, native_enum=False),
        nullable=True,
    )
    age_min_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    age_max_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    range_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    range_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    qualitative_expected: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # REQUIRES LABORATORY/CLINICAL VALIDATION - never populated by this
    # codebase; only used by the interpretation engine when configured.
    critical_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    critical_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    template_parameter: Mapped["LaboratoryTemplateParameter"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryReferenceRange id={self.id} template_parameter_id={self.template_parameter_id}>"
