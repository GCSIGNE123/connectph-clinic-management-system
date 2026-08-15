"""Laboratory Templates (Phase 10): the Administrator-configurable test
catalog that lets new tests (e.g. "HbA1c") be added entirely through the
API/UI, no code changes - see spec's "architecture must support adding new
tests without code changes". `LaboratoryTemplateParameter` rows describe
each result parameter a test produces (a CBC template has ~10 parameters).

Per-sex reference ranges were considered and intentionally simplified to a
single `normal_range` free-text field per parameter (e.g. "12.0-16.0" or
"Negative") rather than separate male/female/general columns - most PH
clinic lab slips print one range per parameter and doctors are used to
reading a combined range; splitting it out is scope creep for this phase
and can be added additively later without a breaking migration.

Feature 3 (Automatic Interpretation): `normal_range` above stays exactly
as-is (the human-readable display string, e.g. on a printed slip) - it is
NOT parsed. `range_low`/`range_high`/`expected_normal_text` below are a
separate, structured, OPTIONAL source of truth an Administrator can
additionally fill in per parameter, which `laboratory_interpretation.
interpret_result()` reads to auto-compute BELOW/NORMAL/ABOVE (numeric) or
NORMAL/ABNORMAL (qualitative). All three are nullable and default to
unset - an existing template with only a free-text `normal_range` keeps
working exactly as before, just without auto-interpretation until an
Administrator opts a parameter in by filling these in too. No clinical
range values are seeded anywhere in this codebase; only the parameter
catalog structure (name/unit) is - see `DEFAULT_LABORATORY_TEMPLATES`.
"""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import LegacyMixin, SoftDeleteMixin, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.laboratory_result import LaboratoryResultType


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class LaboratoryTemplate(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_templates"

    test_name: Mapped[str] = mapped_column(String(255), nullable=False)
    test_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    specimen_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    default_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    turnaround_time_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    parameters: Mapped[list["LaboratoryTemplateParameter"]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="LaboratoryTemplateParameter.display_order"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryTemplate id={self.id} test_name={self.test_name!r}>"


class LaboratoryTemplateParameter(UUIDPrimaryKeyMixin, TenantMixin, LegacyMixin, Base):
    __tablename__ = "laboratory_template_parameters"

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("laboratory_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parameter_name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    normal_range: Mapped[str | None] = mapped_column(String(100), nullable=True)
    result_type: Mapped[LaboratoryResultType] = mapped_column(
        SAEnum(LaboratoryResultType, name="laboratory_result_type_param", values_callable=_enum_values, native_enum=False),
        nullable=False, default=LaboratoryResultType.NUMERIC, server_default=LaboratoryResultType.NUMERIC.value,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Feature 3: structured, optional. Numeric parameters use range_low/
    # range_high; qualitative (Text) parameters use expected_normal_text.
    # Left unset, auto-interpretation simply never activates for that
    # parameter - see module docstring.
    range_low: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    range_high: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    expected_normal_text: Mapped[str | None] = mapped_column(String(100), nullable=True)

    template: Mapped["LaboratoryTemplate"] = relationship(back_populates="parameters")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LaboratoryTemplateParameter id={self.id} parameter_name={self.parameter_name!r}>"


# Feature 3: starter template STRUCTURE only (parameter names + units, both
# objective/standardized, not clinical judgment calls) - deliberately no
# `range_low`/`range_high`/`expected_normal_text` here. Reference ranges
# vary by lab/analyzer/methodology and must be entered by clinic/medical
# staff via the Template admin UI before auto-interpretation activates for
# any of these parameters; until then they behave exactly as an
# already-existing template with only a free-text `normal_range` does
# today (interpretation stays manual). Seeded via
# `LaboratoryService.seed_default_templates` (same opt-in,
# call-explicitly-per-clinic pattern as `DEFAULT_SERVICES`/
# `ClinicServiceCatalogService.seed_defaults` - never auto-run).
DEFAULT_LABORATORY_TEMPLATES: list[dict] = [
    {
        "test_name": "CBC",
        "test_category": "Hematology",
        "specimen_type": "Whole Blood",
        "parameters": [
            {"parameter_name": "Hemoglobin", "unit": "g/dL", "result_type": "Numeric"},
            {"parameter_name": "Hematocrit", "unit": "%", "result_type": "Numeric"},
            {"parameter_name": "WBC Count", "unit": "x10^9/L", "result_type": "Numeric"},
            {"parameter_name": "RBC Count", "unit": "x10^12/L", "result_type": "Numeric"},
            {"parameter_name": "Platelet Count", "unit": "x10^9/L", "result_type": "Numeric"},
            {"parameter_name": "MCV", "unit": "fL", "result_type": "Numeric"},
            {"parameter_name": "MCH", "unit": "pg", "result_type": "Numeric"},
            {"parameter_name": "MCHC", "unit": "g/dL", "result_type": "Numeric"},
            {"parameter_name": "Neutrophils", "unit": "%", "result_type": "Numeric"},
            {"parameter_name": "Lymphocytes", "unit": "%", "result_type": "Numeric"},
        ],
    },
    {
        "test_name": "Urinalysis",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Urine",
        "parameters": [
            {"parameter_name": "Color", "unit": None, "result_type": "Text"},
            {"parameter_name": "Appearance", "unit": None, "result_type": "Text"},
            {"parameter_name": "Specific Gravity", "unit": None, "result_type": "Numeric"},
            {"parameter_name": "pH", "unit": None, "result_type": "Numeric"},
            {"parameter_name": "Protein", "unit": None, "result_type": "Text"},
            {"parameter_name": "Glucose", "unit": None, "result_type": "Text"},
            {"parameter_name": "Ketones", "unit": None, "result_type": "Text"},
            {"parameter_name": "Blood", "unit": None, "result_type": "Text"},
            {"parameter_name": "RBC", "unit": "/hpf", "result_type": "Numeric"},
            {"parameter_name": "WBC", "unit": "/hpf", "result_type": "Numeric"},
            {"parameter_name": "Bacteria", "unit": None, "result_type": "Text"},
        ],
    },
]
