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
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
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

    # Phase 2A (Structured Result Backend Foundation): additive. `options`
    # holds a kind-specific structured definition - e.g. a Categorical
    # parameter's choice list (["A","B","AB","O"]) or a Microscopy
    # parameter's sub-field list - left null (the default for every
    # existing Numeric/Text parameter) until an Administrator configures a
    # new-kind parameter; result_type/normal_range/range_low/range_high/
    # expected_normal_text are all unaffected. `requires_site` flags a
    # parameter whose result needs a specimen site captured per entry
    # (e.g. "KOH Mount per site") - default False, so every existing
    # parameter's behavior is unchanged.
    options: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    requires_site: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # Phase 4A (Urinalysis): additive, nullable, free-text grouping label
    # (e.g. "Physical Examination", "Chemical Examination", "Microscopic
    # Examination") - deliberately generic, not a Urinalysis-specific
    # concept, so any future multi-section test (panel-style templates)
    # can reuse it. Left null (the default for every existing CBC/Blood
    # Typing/legacy parameter) when a template has no natural sections;
    # purely a display/grouping hint - carries no validation or
    # interpretation behavior of its own.
    section: Mapped[str | None] = mapped_column(String(100), nullable=True)

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
    # Phase 4A: restructured from the original 11-parameter Text/Numeric-only
    # list into three sections (Physical/Chemical/Microscopic), matching a
    # realistic Urinalysis report shape, still using only the existing
    # Numeric/Text/Categorical kinds - see laboratory_service.py's
    # docstring note / the Phase 4A report for why Microscopy needed no new
    # architecture. Categorical parameters below (Color, Transparency, and
    # the reagent-strip chemistry rows) deliberately have `options=None` -
    # this project has no existing authoritative option-vocabulary data for
    # them, and Phase 4A explicitly forbids inventing one; an Administrator
    # must configure the actual options via the Template admin UI before
    # these render as real Categorical selects (a Categorical parameter
    # with no options configured behaves as an inert placeholder - see
    # `LaboratoryService._validate_categorical_value`, which no-ops rather
    # than either rejecting-everything or accepting-anything until options
    # are configured). REQUIRES LABORATORY/CLINICAL VALIDATION before use.
    # Microscopic Epithelial Cells/Mucus Threads/Crystals/Casts stay Text
    # (free-text descriptive) for the same reason - no authoritative fixed
    # vocabulary exists in this project to populate as Categorical options.
    {
        "test_name": "Urinalysis",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Urine",
        "parameters": [
            # --- Physical Examination ---
            {"parameter_name": "Color", "unit": None, "result_type": "Categorical", "options": None, "section": "Physical Examination"},
            {"parameter_name": "Transparency", "unit": None, "result_type": "Categorical", "options": None, "section": "Physical Examination"},
            {"parameter_name": "Specific Gravity", "unit": None, "result_type": "Numeric", "section": "Physical Examination"},
            {"parameter_name": "pH", "unit": None, "result_type": "Numeric", "section": "Physical Examination"},
            # --- Chemical Examination ---
            {"parameter_name": "Protein", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            {"parameter_name": "Glucose", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            {"parameter_name": "Ketones", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            {"parameter_name": "Blood", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            {"parameter_name": "Bilirubin", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            {"parameter_name": "Urobilinogen", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            {"parameter_name": "Nitrite", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            {"parameter_name": "Leukocytes", "unit": None, "result_type": "Categorical", "options": None, "section": "Chemical Examination"},
            # --- Microscopic Examination ---
            {"parameter_name": "RBC", "unit": "/hpf", "result_type": "Numeric", "section": "Microscopic Examination"},
            {"parameter_name": "WBC", "unit": "/hpf", "result_type": "Numeric", "section": "Microscopic Examination"},
            {"parameter_name": "Epithelial Cells", "unit": None, "result_type": "Text", "section": "Microscopic Examination"},
            {"parameter_name": "Bacteria", "unit": None, "result_type": "Text", "section": "Microscopic Examination"},
            {"parameter_name": "Mucus Threads", "unit": None, "result_type": "Text", "section": "Microscopic Examination"},
            {"parameter_name": "Crystals", "unit": None, "result_type": "Text", "section": "Microscopic Examination"},
            {"parameter_name": "Casts", "unit": None, "result_type": "Text", "section": "Microscopic Examination"},
        ],
    },
    # Phase 3: the first Categorical starter template - options are the
    # fixed, standardized ABO/Rh vocabulary (not a clinical judgment call,
    # same "objective/standardized structure only" bar as CBC/Urinalysis's
    # own parameter names/units above) - no reference range or
    # interpretation is configured or applicable to a categorical result.
    {
        "test_name": "Blood Typing",
        "test_category": "Immunohematology",
        "specimen_type": "Whole Blood",
        "parameters": [
            {"parameter_name": "ABO Group", "result_type": "Categorical", "options": ["A", "B", "AB", "O"]},
            {"parameter_name": "Rh Factor", "result_type": "Categorical", "options": ["Positive", "Negative"]},
        ],
    },
    # Phase 4C: qualitative rapid-test/immunoassay templates. Every one of
    # these uses the same generic Categorical-with-unconfigured-options
    # pattern already proven for Urinalysis's chemistry rows - `options`
    # deliberately left null (no authoritative reporting vocabulary exists
    # in this project for any of them). REQUIRES LABORATORY/CLINICAL
    # VALIDATION before an Administrator configures real options. See the
    # Phase 4C report for the full per-test reasoning (in particular why
    # HCG isn't Numeric, and why VDRL is a single Categorical "Result"
    # rather than using the reserved but not-yet-fully-supported `Titer`
    # result type - see `laboratory_result.py`'s `LaboratoryResultType`
    # docstring and `ResultEntryDialog.tsx`'s Phase 4C note).
    {
        "test_name": "HCG (Serum)",
        "test_category": "Immunology",
        "specimen_type": "Serum",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None}],
    },
    {
        "test_name": "HCG (Urine)",
        "test_category": "Immunology",
        "specimen_type": "Urine",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None}],
    },
    {
        "test_name": "Hepatitis B Antigen (HBsAg)",
        "test_category": "Immunology",
        "specimen_type": "Whole Blood",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None}],
    },
    {
        "test_name": "Hepatitis A Virus Test (HAV)",
        "test_category": "Immunology",
        "specimen_type": "Whole Blood",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None}],
    },
    {
        "test_name": "VDRL / Syphilis Test",
        "test_category": "Immunology",
        "specimen_type": "Serum",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None}],
    },
    # Dengue Rapid Test: NS1/IgM/IgG are the industry-standard analyte
    # NAMES a combo dengue rapid test kit reports (structural fact, the
    # same category of "objective structure, not a clinical judgment call"
    # already established for CBC's parameter names and Blood Typing's
    # ABO/Rh naming) - three independent generic Categorical parameters,
    # proving the existing architecture already supports a multi-component
    # qualitative panel with no new structured JSON. Each parameter's
    # options are still left unconfigured (REQUIRES LABORATORY/CLINICAL
    # VALIDATION) - only the analyte breakdown is structural, the
    # Positive/Negative-style vocabulary is not assumed.
    {
        "test_name": "Dengue Rapid Test",
        "test_category": "Immunology",
        "specimen_type": "Whole Blood",
        "parameters": [
            {"parameter_name": "NS1", "result_type": "Categorical", "options": None},
            {"parameter_name": "IgM", "result_type": "Categorical", "options": None},
            {"parameter_name": "IgG", "result_type": "Categorical", "options": None},
        ],
    },
    # Phase 4D: Stool Exam, Fecal Occult Blood, Sputum Exam, Gram Stain,
    # Trichomonas Vaginalis Mount, KOH Mount. Every parameter below uses
    # only Numeric/Text/Categorical - `Microscopy`/`Titer` were
    # investigated and confirmed to have the same unwired frontend
    # lifecycle gap Phase 4C found for Titer (see laboratory_service.py's
    # module docstring note and the Phase 4D report), so neither is used
    # anywhere in this phase. All Categorical `options` are deliberately
    # left null - REQUIRES LABORATORY/CLINICAL VALIDATION - no
    # organism/reagent/positive-negative vocabulary is invented.
    {
        "test_name": "Stool Exam (Direct Mount)",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Stool",
        "parameters": [
            {"parameter_name": "Color", "result_type": "Categorical", "options": None, "section": "Macroscopic Examination"},
            {"parameter_name": "Consistency", "result_type": "Categorical", "options": None, "section": "Macroscopic Examination"},
            {"parameter_name": "Microscopic Findings", "result_type": "Text", "section": "Microscopic Examination"},
        ],
    },
    {
        "test_name": "Fecal Occult Blood Test",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Stool",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None}],
    },
    # Single free-descriptive Text parameter - deliberately not split into
    # Gross/Microscopic sub-fields; unlike Stool/Urinalysis, no prior
    # project requirement or established convention justifies a multi-
    # parameter structure for Sputum Exam (Phase 4D's own explicit
    # instruction: don't create structure merely because it's possible).
    {
        "test_name": "Sputum Exam",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Sputum",
        "parameters": [{"parameter_name": "Result", "result_type": "Text"}],
    },
    # Gram Stain findings are inherently free-text descriptive (e.g.
    # organism morphology/arrangement) - generic Text is sufficient and
    # already fully supported end-to-end; `Microscopy` is deliberately NOT
    # used here (see module-level Phase 4D note).
    {
        "test_name": "Gram Stain",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Varies",
        "parameters": [{"parameter_name": "Result", "result_type": "Text"}],
    },
    # No site: the test's own name already specifies the single implied
    # specimen site (vaginal) - unlike KOH Mount, nothing in this project
    # or the phase spec indicates Trichomonas Vaginalis Mount varies by
    # collection site, so `requires_site` is not set.
    {
        "test_name": "Trichomonas Vaginalis Mount",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Vaginal Swab",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None}],
    },
    # KOH Mount per site: `requires_site=True` is the existing Phase 2A
    # mechanism this test proves out - no site vocabulary is seeded
    # (REQUIRES LABORATORY/CLINICAL VALIDATION would apply to any preset
    # site list too, so the technician enters the actual specimen site as
    # free text per result, same as any other free-text field).
    {
        "test_name": "KOH Mount",
        "test_category": "Clinical Microscopy",
        "specimen_type": "Varies (per site)",
        "parameters": [{"parameter_name": "Result", "result_type": "Categorical", "options": None, "requires_site": True}],
    },
]
