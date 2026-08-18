"""Laboratory structured result backend foundation (Phase 2A).

Purely additive - extends the existing LaboratoryTemplate ->
LaboratoryTemplateParameter -> LaboratoryResult architecture, does not
replace or restructure it. No existing column is altered, renamed, or
dropped; no backfill is required since every new column is nullable (or a
boolean with a safe `false` default).

Adds:
- `laboratory_template_parameters.options` (JSONB, nullable) - a
  Categorical parameter's choice list or a Microscopy parameter's sub-field
  definition. Null for every existing Numeric/Text parameter.
- `laboratory_template_parameters.requires_site` (boolean, NOT NULL,
  default False) - flags a parameter whose result needs a specimen site
  captured per entry (e.g. "KOH Mount per site").
- `laboratory_results.site` (varchar(100), nullable) - the site captured
  for a `requires_site` parameter's result.
- `laboratory_results.structured_value` (JSONB, nullable) - Categorical/
  Microscopy kind-specific result fields. `numeric_value`/`text_value`
  remain the storage for Numeric/Text/Titer results, unchanged.
- new table `laboratory_reference_ranges` - additive companion to
  `laboratory_template_parameters.range_low`/`range_high`/
  `expected_normal_text`, which remain the default/fallback range and are
  NOT touched by this migration. Supports a future demographic-specific
  (sex/age) reference range per template parameter, versioned via
  `is_active`/`effective_from` rather than hard-deleting superseded rows -
  see `app/models/laboratory_reference_range.py`'s module docstring.

`LaboratoryResultType`/`LaboratoryInterpretation`'s new enum members
(Categorical/Microscopy/Titer, Critical Low/Critical High) require no DDL
here - both columns were created in migration 0011 as plain
`sa.String(length=20)` (Python-side `Enum(..., native_enum=False)`), not a
native Postgres enum type, so new allowed string values are a pure
application-level change (verified against 0011_laboratory_management.py
and the current model definitions before writing this migration).

Revision ID: 0031_lab_structured_results
Revises: 0030_laboratory_reference_ranges
Create Date: 2026-08-17

Note: the revision id is shortened to "0031_lab_structured_results" (28
chars) rather than the fuller "0031_laboratory_structured_results" (35
chars) - `alembic_version.version_num` is `VARCHAR(32)` in this project
(confirmed by testing against the local dev database; the prior revision
"0030_laboratory_reference_ranges" is exactly 32 chars), so a longer id
would fail the final version-stamp UPDATE after the DDL already ran.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_lab_structured_results"
down_revision: str | None = "0030_laboratory_reference_ranges"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("laboratory_template_parameters", sa.Column("options", postgresql.JSONB(), nullable=True))
    op.add_column(
        "laboratory_template_parameters",
        sa.Column("requires_site", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.add_column("laboratory_results", sa.Column("site", sa.String(length=100), nullable=True))
    op.add_column("laboratory_results", sa.Column("structured_value", postgresql.JSONB(), nullable=True))

    op.create_table(
        "laboratory_reference_ranges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("clinic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clinics.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "template_parameter_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("laboratory_template_parameters.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("sex", sa.String(length=20), nullable=True),
        sa.Column("age_min_years", sa.Integer(), nullable=True),
        sa.Column("age_max_years", sa.Integer(), nullable=True),
        sa.Column("range_low", sa.Numeric(14, 4), nullable=True),
        sa.Column("range_high", sa.Numeric(14, 4), nullable=True),
        sa.Column("qualitative_expected", sa.String(length=100), nullable=True),
        sa.Column("critical_low", sa.Numeric(14, 4), nullable=True),
        sa.Column("critical_high", sa.Numeric(14, 4), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_laboratory_reference_ranges_clinic_id", "laboratory_reference_ranges", ["clinic_id"])
    op.create_index(
        "ix_laboratory_reference_ranges_template_parameter_id", "laboratory_reference_ranges", ["template_parameter_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_laboratory_reference_ranges_template_parameter_id", table_name="laboratory_reference_ranges")
    op.drop_index("ix_laboratory_reference_ranges_clinic_id", table_name="laboratory_reference_ranges")
    op.drop_table("laboratory_reference_ranges")

    op.drop_column("laboratory_results", "structured_value")
    op.drop_column("laboratory_results", "site")

    op.drop_column("laboratory_template_parameters", "requires_site")
    op.drop_column("laboratory_template_parameters", "options")
